from rpython.rlib import jit
from rpython.rlib.buffer import SubBuffer
from rpython.rlib.rstruct.error import StructError, StructOverflowError
from rpython.rlib.rstruct.formatiterator import CalcSizeFormatIterator
from rpython.tool.sourcetools import func_with_new_name

from pypy.interpreter.baseobjspace import W_Root
from pypy.interpreter.gateway import interp2app, unwrap_spec
from pypy.interpreter.error import OperationError, oefmt
from pypy.interpreter.typedef import TypeDef, interp_attrproperty
from pypy.module.struct.formatiterator import (
    PackFormatIterator, UnpackFormatIterator
)


@unwrap_spec(format=str)
def calcsize(space, format):
    return space.wrap(_calcsize(space, format))


def _calcsize(space, format):
    fmtiter = CalcSizeFormatIterator()
    try:
        fmtiter.interpret(format)
    except StructOverflowError, e:
        raise OperationError(space.w_OverflowError, space.wrap(e.msg))
    except StructError, e:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise OperationError(w_error, space.wrap(e.msg))
    return fmtiter.totalsize


@unwrap_spec(format=str)
def pack(space, format, args_w):
    if jit.isconstant(format):
        size = _calcsize(space, format)
    else:
        size = 8
    fmtiter = PackFormatIterator(space, args_w, size)
    try:
        fmtiter.interpret(format)
    except StructOverflowError, e:
        raise OperationError(space.w_OverflowError, space.wrap(e.msg))
    except StructError, e:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise OperationError(w_error, space.wrap(e.msg))
    return space.wrapbytes(fmtiter.result.build())


# XXX inefficient
@unwrap_spec(format=str, offset=int)
def pack_into(space, format, w_buf, offset, args_w):
    res = pack(space, format, args_w).bytes_w(space)
    buf = space.writebuf_w(w_buf)
    if offset < 0:
        offset += buf.getlength()
    size = len(res)
    if offset < 0 or (buf.getlength() - offset) < size:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise oefmt(w_error,
                    "pack_into requires a buffer of at least %d bytes",
                    size)
    buf.setslice(offset, res)


def _unpack(space, format, buf):
    fmtiter = UnpackFormatIterator(space, buf)
    try:
        fmtiter.interpret(format)
    except StructOverflowError, e:
        raise OperationError(space.w_OverflowError, space.wrap(e.msg))
    except StructError, e:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise OperationError(w_error, space.wrap(e.msg))
    return space.newtuple(fmtiter.result_w[:])

def clearcache(space):
    "Clear the internal cache."
    # No cache in this implementation


@unwrap_spec(format=str)
def unpack(space, format, w_str):
    buf = space.getarg_w('s*', w_str)
    return _unpack(space, format, buf)


@unwrap_spec(format=str, offset=int)
def unpack_from(space, format, w_buffer, offset=0):
    size = _calcsize(space, format)
    buf = space.getarg_w('z*', w_buffer)
    if buf is None:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise oefmt(w_error, "unpack_from requires a buffer argument")
    if offset < 0:
        offset += buf.getlength()
    if offset < 0 or (buf.getlength() - offset) < size:
        w_module = space.getbuiltinmodule('struct')
        w_error = space.getattr(w_module, space.wrap('error'))
        raise oefmt(w_error,
                    "unpack_from requires a buffer of at least %d bytes",
                    size)
    buf = SubBuffer(buf, offset, size)
    return _unpack(space, format, buf)


class W_Struct(W_Root):
    _immutable_fields_ = ["format", "size"]

    def __init__(self, space, format):
        self.format = format
        self.size = _calcsize(space, format)

    @unwrap_spec(format=str)
    def descr__new__(space, w_subtype, format):
        self = space.allocate_instance(W_Struct, w_subtype)
        W_Struct.__init__(self, space, format)
        return self

    def wrap_struct_method(name):
        def impl(self, space, __args__):
            w_module = space.getbuiltinmodule('struct')
            w_method = space.getattr(w_module, space.wrap(name))
            return space.call_obj_args(
                w_method, space.wrap(self.format), __args__
            )

        return func_with_new_name(impl, 'descr_' + name)

    descr_pack = wrap_struct_method("pack")
    descr_unpack = wrap_struct_method("unpack")
    descr_pack_into = wrap_struct_method("pack_into")
    descr_unpack_from = wrap_struct_method("unpack_from")


W_Struct.typedef = TypeDef("Struct",
    __new__=interp2app(W_Struct.descr__new__.im_func),
    format=interp_attrproperty("format", cls=W_Struct),
    size=interp_attrproperty("size", cls=W_Struct),

    pack=interp2app(W_Struct.descr_pack),
    unpack=interp2app(W_Struct.descr_unpack),
    pack_into=interp2app(W_Struct.descr_pack_into),
    unpack_from=interp2app(W_Struct.descr_unpack_from),
)
