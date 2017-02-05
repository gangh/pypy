
from pypy.interpreter.error import OperationError, oefmt
from pypy.interpreter.gateway import unwrap_spec

@unwrap_spec(type=str)
def newdict(space, type):
    """ newdict(type)

    Create a normal dict with a special implementation strategy.

    type is a string and can be:

    * "module" - equivalent to some_module.__dict__

    * "instance" - equivalent to an instance dict with a not-changing-much
                   set of keys

    * "kwargs" - keyword args dict equivalent of what you get from **kwargs
                 in a function, optimized for passing around

    * "strdict" - string-key only dict. This one should be chosen automatically
    """
    if type == 'module':
        return space.newdict(module=True)
    elif type == 'instance':
        return space.newdict(instance=True)
    elif type == 'kwargs':
        return space.newdict(kwargs=True)
    elif type == 'strdict':
        return space.newdict(strdict=True)
    else:
        raise oefmt(space.w_TypeError, "unknown type of dict %s", type)

def reversed_dict(space, w_obj):
    """Enumerate the keys in a dictionary object in reversed order.

    This is a __pypy__ function instead of being simply done by calling
    reversed(), for CPython compatibility: dictionaries are only ordered
    on PyPy.  You should use the collections.OrderedDict class for cases
    where ordering is important.  That class implements __reversed__ by
    calling __pypy__.reversed_dict().
    """
    from pypy.objspace.std.dictmultiobject import W_DictMultiObject
    if not isinstance(w_obj, W_DictMultiObject):
        raise OperationError(space.w_TypeError, space.w_None)
    return w_obj.nondescr_reversed_dict(space)

@unwrap_spec(last=bool)
def move_to_end(space, w_obj, w_key, last=True):
    """Move the key in a dictionary object into the first or last position.

    This is a __pypy__ function instead of being simply done by calling
    dict.move_to_end(), for CPython compatibility: dictionaries are only
    ordered on PyPy.  You should use the collections.OrderedDict class for
    cases where ordering is important.  That class implements the
    move_to_end() method by calling __pypy__.move_to_end().
    """
    from pypy.objspace.std.dictmultiobject import W_DictMultiObject
    if not isinstance(w_obj, W_DictMultiObject):
        raise OperationError(space.w_TypeError, space.w_None)
    return w_obj.nondescr_move_to_end(space, w_key, last)
