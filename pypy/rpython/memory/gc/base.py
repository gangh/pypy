from pypy.rpython.lltypesystem import lltype, llmemory, llarena
from pypy.rlib.debug import ll_assert
from pypy.rpython.memory.gcheader import GCHeaderBuilder
from pypy.rpython.memory.support import DEFAULT_CHUNK_SIZE
from pypy.rpython.memory.support import get_address_stack, get_address_deque
from pypy.rpython.memory.support import AddressDict
from pypy.rpython.lltypesystem.llmemory import NULL, raw_malloc_usage

class GCBase(object):
    _alloc_flavor_ = "raw"
    moving_gc = False
    needs_write_barrier = False
    malloc_zero_filled = False
    prebuilt_gc_objects_are_static_roots = True
    can_realloc = False

    def can_malloc_nonmovable(self):
        return not self.moving_gc

    # The following flag enables costly consistency checks after each
    # collection.  It is automatically set to True by test_gc.py.  The
    # checking logic is translatable, so the flag can be set to True
    # here before translation.
    DEBUG = False

    def set_query_functions(self, is_varsize, has_gcptr_in_varsize,
                            is_gcarrayofgcptr,
                            getfinalizer,
                            offsets_to_gc_pointers,
                            fixed_size, varsize_item_sizes,
                            varsize_offset_to_variable_part,
                            varsize_offset_to_length,
                            varsize_offsets_to_gcpointers_in_var_part,
                            weakpointer_offset):
        self.getfinalizer = getfinalizer
        self.is_varsize = is_varsize
        self.has_gcptr_in_varsize = has_gcptr_in_varsize
        self.is_gcarrayofgcptr = is_gcarrayofgcptr
        self.offsets_to_gc_pointers = offsets_to_gc_pointers
        self.fixed_size = fixed_size
        self.varsize_item_sizes = varsize_item_sizes
        self.varsize_offset_to_variable_part = varsize_offset_to_variable_part
        self.varsize_offset_to_length = varsize_offset_to_length
        self.varsize_offsets_to_gcpointers_in_var_part = varsize_offsets_to_gcpointers_in_var_part
        self.weakpointer_offset = weakpointer_offset

    def set_root_walker(self, root_walker):
        self.root_walker = root_walker

    def write_barrier(self, newvalue, addr_struct):
        pass

    def setup(self):
        pass

    def statistics(self, index):
        return -1

    def size_gc_header(self, typeid=0):
        return self.gcheaderbuilder.size_gc_header

    def malloc(self, typeid, length=0, zero=False):
        """For testing.  The interface used by the gctransformer is
        the four malloc_[fixed,var]size[_clear]() functions.
        """
        # Rules about fallbacks in case of missing malloc methods:
        #  * malloc_fixedsize_clear() and malloc_varsize_clear() are mandatory
        #  * malloc_fixedsize() and malloc_varsize() fallback to the above
        # XXX: as of r49360, gctransformer.framework never inserts calls
        # to malloc_varsize(), but always uses malloc_varsize_clear()

        size = self.fixed_size(typeid)
        needs_finalizer = bool(self.getfinalizer(typeid))
        contains_weakptr = self.weakpointer_offset(typeid) >= 0
        assert not (needs_finalizer and contains_weakptr)
        if self.is_varsize(typeid):
            assert not contains_weakptr
            itemsize = self.varsize_item_sizes(typeid)
            offset_to_length = self.varsize_offset_to_length(typeid)
            if zero or not hasattr(self, 'malloc_varsize'):
                malloc_varsize = self.malloc_varsize_clear
            else:
                malloc_varsize = self.malloc_varsize
            ref = malloc_varsize(typeid, length, size, itemsize,
                                 offset_to_length, True, needs_finalizer)
        else:
            if zero or not hasattr(self, 'malloc_fixedsize'):
                malloc_fixedsize = self.malloc_fixedsize_clear
            else:
                malloc_fixedsize = self.malloc_fixedsize
            ref = malloc_fixedsize(typeid, size, True, needs_finalizer,
                                   contains_weakptr)
        # lots of cast and reverse-cast around...
        return llmemory.cast_ptr_to_adr(ref)

    def malloc_nonmovable(self, typeid, length=0, zero=False):
        return self.malloc(typeid, length, zero)

    def id(self, ptr):
        return lltype.cast_ptr_to_int(ptr)

    def can_move(self, addr):
        return False

    def set_max_heap_size(self, size):
        pass

    def x_swap_pool(self, newpool):
        return newpool

    def x_clone(self, clonedata):
        raise RuntimeError("no support for x_clone in the GC")

    def trace(self, obj, callback, arg):
        """Enumerate the locations inside the given obj that can contain
        GC pointers.  For each such location, callback(pointer, arg) is
        called, where 'pointer' is an address inside the object.
        Typically, 'callback' is a bound method and 'arg' can be None.
        """
        typeid = self.get_type_id(obj)
        if self.is_gcarrayofgcptr(typeid):
            # a performance shortcut for GcArray(gcptr)
            length = (obj + llmemory.gcarrayofptr_lengthoffset).signed[0]
            item = obj + llmemory.gcarrayofptr_itemsoffset
            while length > 0:
                callback(item, arg)
                item += llmemory.gcarrayofptr_singleitemoffset
                length -= 1
            return
        offsets = self.offsets_to_gc_pointers(typeid)
        i = 0
        while i < len(offsets):
            callback(obj + offsets[i], arg)
            i += 1
        if self.has_gcptr_in_varsize(typeid):
            item = obj + self.varsize_offset_to_variable_part(typeid)
            length = (obj + self.varsize_offset_to_length(typeid)).signed[0]
            offsets = self.varsize_offsets_to_gcpointers_in_var_part(typeid)
            itemlength = self.varsize_item_sizes(typeid)
            while length > 0:
                j = 0
                while j < len(offsets):
                    callback(item + offsets[j], arg)
                    j += 1
                item += itemlength
                length -= 1
    trace._annspecialcase_ = 'specialize:arg(2)'

    def debug_check_consistency(self):
        """To use after a collection.  If self.DEBUG is set, this
        enumerates all roots and traces all objects to check if we didn't
        accidentally free a reachable object or forgot to update a pointer
        to an object that moved.
        """
        if self.DEBUG:
            from pypy.rlib.objectmodel import we_are_translated
            from pypy.rpython.memory.support import AddressDict
            self._debug_seen = AddressDict()
            self._debug_pending = self.AddressStack()
            if not we_are_translated():
                self.root_walker._walk_prebuilt_gc(self._debug_record)
            callback = GCBase._debug_callback
            self.root_walker.walk_roots(callback, callback, callback)
            pending = self._debug_pending
            while pending.non_empty():
                obj = pending.pop()
                self.debug_check_object(obj)
                self.trace(obj, self._debug_callback2, None)
            self._debug_seen.delete()
            self._debug_pending.delete()

    def _debug_record(self, obj):
        seen = self._debug_seen
        if not seen.contains(obj):
            seen.add(obj)
            self._debug_pending.append(obj)
    def _debug_callback(self, root):
        obj = root.address[0]
        ll_assert(bool(obj), "NULL address from walk_roots()")
        self._debug_record(obj)
    def _debug_callback2(self, pointer, ignored):
        obj = pointer.address[0]
        if obj:
            self._debug_record(obj)

    def debug_check_object(self, obj):
        pass

first_gcflag = 1 << 16

class MovingGCBase(GCBase):
    moving_gc = True

    def __init__(self, chunk_size=DEFAULT_CHUNK_SIZE):
        GCBase.__init__(self)
        self.gcheaderbuilder = GCHeaderBuilder(self.HDR)
        self.AddressStack = get_address_stack(chunk_size)
        self.AddressDeque = get_address_deque(chunk_size)
        self.AddressDict = AddressDict
        self.finalizer_lock_count = 0
        self.id_free_list = self.AddressStack()
        self.next_free_id = 1
        self.red_zone = 0

    def setup(self):
        self.objects_with_finalizers = self.AddressDeque()
        self.run_finalizers = self.AddressDeque()
        self.objects_with_weakrefs = self.AddressStack()
        self.objects_with_id = self.AddressDict()

    def can_move(self, addr):
        return True

    def header(self, addr):
        addr -= self.gcheaderbuilder.size_gc_header
        return llmemory.cast_adr_to_ptr(addr, lltype.Ptr(self.HDR))

    def init_gc_object(self, addr, typeid, flags=0):
        hdr = llmemory.cast_adr_to_ptr(addr, lltype.Ptr(self.HDR))
        hdr.tid = typeid | flags

    def get_size(self, obj):
        typeid = self.get_type_id(obj)
        size = self.fixed_size(typeid)
        if self.is_varsize(typeid):
            lenaddr = obj + self.varsize_offset_to_length(typeid)
            length = lenaddr.signed[0]
            size += length * self.varsize_item_sizes(typeid)
            size = llarena.round_up_for_allocation(size)
        return size

    def record_red_zone(self):
        # red zone: if the space is more than 80% full, the next collection
        # should double its size.  If it is more than 66% full twice in a row,
        # then it should double its size too.  (XXX adjust)
        # The goal is to avoid many repeated collection that don't free a lot
        # of memory each, if the size of the live object set is just below the
        # size of the space.
        free_after_collection = self.top_of_space - self.free
        if free_after_collection > self.space_size // 3:
            self.red_zone = 0
        else:
            self.red_zone += 1
            if free_after_collection < self.space_size // 5:
                self.red_zone += 1

def choose_gc_from_config(config):
    """Return a (GCClass, GC_PARAMS) from the given config object.
    """
    if config.translation.gctransformer != "framework":   # for tests
        config.translation.gc = "marksweep"     # crash if inconsistent

    classes = {"marksweep": "marksweep.MarkSweepGC",
               "statistics": "marksweep.PrintingMarkSweepGC",
               "semispace": "semispace.SemiSpaceGC",
               "generation": "generation.GenerationGC",
               "hybrid": "hybrid.HybridGC",
               "markcompact" : "markcompact.MarkCompactGC",
               }
    try:
        modulename, classname = classes[config.translation.gc].split('.')
    except KeyError:
        raise ValueError("unknown value for translation.gc: %r" % (
            config.translation.gc,))
    module = __import__("pypy.rpython.memory.gc." + modulename,
                        globals(), locals(), [classname])
    GCClass = getattr(module, classname)
    return GCClass, GCClass.TRANSLATION_PARAMS
