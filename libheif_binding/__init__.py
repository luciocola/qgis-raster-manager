"""
libheif_binding — Pythonic wrapper around the libheif SWIG extension.

Provides:
    HeifContext     — context manager wrapping heif_context*
    ImageHandle     — context manager wrapping heif_image_handle*
    MetadataBlock   — thin view over one metadata block on an image handle
    HeifError       — exception raised on non-zero heif_error codes
    SWIG_BINDING_AVAILABLE — bool flag; False when the .so has not been compiled

Quick-start
-----------
    from libheif_binding import HeifContext

    with HeifContext.from_file("image.heif") as ctx:
        for image_id in ctx.top_level_image_ids():
            with ctx.get_image_handle(image_id) as handle:
                print(handle.width, handle.height, handle.is_primary)
                for block in handle.metadata_blocks():
                    print(block.item_type, block.content_type, block.size)
                    data = block.read()   # bytes | None

    # High-level helpers used by heif_processor.py
    with HeifContext.from_file("tb21_file.heif") as ctx:
        mode = ctx.detect_tiling_mode()          # 'grid' | 'tili' | 'unci' | None
        data, fmt = ctx.find_rdf_metadata()      # (bytes, 'turtle'|'xml') | (None, None)

Build the extension first (from this directory):
    ./build.sh
or:
    python setup.py build_ext --inplace
"""

from __future__ import annotations

# ── Try to import the compiled SWIG extension ─────────────────────────
try:
    from . import _libheif_core as _lib
    SWIG_BINDING_AVAILABLE: bool = True
except ImportError:
    try:
        import _libheif_core as _lib  # type: ignore[no-redef]
        SWIG_BINDING_AVAILABLE = True
    except ImportError:
        SWIG_BINDING_AVAILABLE = False
        _lib = None  # type: ignore[assignment]


# ── Exception ─────────────────────────────────────────────────────────

class HeifError(Exception):
    """Raised when a libheif C API call returns a non-zero error code."""

    def __init__(self, code: int, subcode: int, message: str) -> None:
        super().__init__(f"libheif error {code}/{subcode}: {message}")
        self.code    = code
        self.subcode = subcode


def _check(err: object) -> None:
    """Raise HeifError if *err* indicates failure (code != 0)."""
    if err.code != 0:  # type: ignore[union-attr]
        raise HeifError(err.code, err.subcode, err.message or "")  # type: ignore[union-attr]


# ── MetadataBlock ─────────────────────────────────────────────────────

class MetadataBlock:
    """A single metadata block attached to a HEIF image item.

    Instances are lightweight view objects; the underlying data lives in
    the parent ``ImageHandle`` (and therefore the ``HeifContext``).  Do not
    use a ``MetadataBlock`` after its parent ``ImageHandle`` has been released.
    """

    __slots__ = ("_handle", "_id")

    def __init__(self, handle_ptr: object, block_id: int) -> None:
        self._handle = handle_ptr
        self._id     = block_id

    @property
    def item_type(self) -> str:
        """ISO BMFF item type string, e.g. ``'mime'``, ``'Exif'``, ``'XMP '``."""
        val = _lib.heif_image_handle_get_metadata_type(self._handle, self._id)
        return val or ""

    @property
    def content_type(self) -> str:
        """MIME content-type of the block, e.g. ``'text/turtle'``, ``'application/rdf+xml'``."""
        val = _lib.heif_image_handle_get_metadata_content_type(self._handle, self._id)
        return val or ""

    @property
    def size(self) -> int:
        """Byte length of the raw metadata payload."""
        return _lib.heif_image_handle_get_metadata_size(self._handle, self._id)

    def read(self) -> bytes | None:
        """Return the raw metadata payload as ``bytes``, or ``None`` on failure."""
        return _lib.heif_get_metadata_bytes(self._handle, self._id)


# ── ImageHandle ───────────────────────────────────────────────────────

class ImageHandle:
    """Wrapper around a ``heif_image_handle*``.

    Acquire via :py:meth:`HeifContext.get_image_handle` and use as a context
    manager to guarantee the handle is released::

        with ctx.get_image_handle(image_id) as handle:
            print(handle.width, handle.height)
    """

    __slots__ = ("_ptr",)

    def __init__(self, ptr: object) -> None:
        self._ptr = ptr

    # ── Context-manager protocol ───────────────────────────────────────
    def __enter__(self) -> "ImageHandle":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def release(self) -> None:
        """Explicitly release the underlying ``heif_image_handle*``."""
        if self._ptr is not None:
            _lib.heif_image_handle_release(self._ptr)
            self._ptr = None

    # ── Properties ────────────────────────────────────────────────────
    @property
    def width(self) -> int:
        return _lib.heif_image_handle_get_width(self._ptr)

    @property
    def height(self) -> int:
        return _lib.heif_image_handle_get_height(self._ptr)

    @property
    def is_primary(self) -> bool:
        return bool(_lib.heif_image_handle_is_primary_image(self._ptr))

    @property
    def item_id(self) -> int:
        return int(_lib.heif_image_handle_get_item_id(self._ptr))

    @property
    def tile_count(self) -> int:
        """Number of tiles; 0 for non-tiled images (libheif ≥ 1.17)."""
        return _lib.heif_image_handle_get_number_of_tiles(self._ptr)

    # ── Metadata ──────────────────────────────────────────────────────
    def metadata_blocks(self, type_filter: str | None = None) -> list[MetadataBlock]:
        """Return all metadata blocks attached to this image, optionally filtered.

        Args:
            type_filter: ISO BMFF item-type string (e.g. ``'mime'``) or ``None``
                         for all blocks.

        Returns:
            A list of :py:class:`MetadataBlock` objects.
        """
        ids = _lib.heif_get_metadata_block_ids(self._ptr, type_filter)
        return [MetadataBlock(self._ptr, bid) for bid in ids]

    def has_content_type(self, content_type: str) -> bool:
        """Return ``True`` if any metadata block carries *content_type*."""
        return any(b.content_type == content_type for b in self.metadata_blocks())


# ── HeifContext ───────────────────────────────────────────────────────

#: MIME content-type strings that indicate RDF metadata, mapped to a short
#: format name ('turtle' or 'xml').
_RDF_CONTENT_TYPES: dict[str, str] = {
    "text/turtle":              "turtle",
    "application/rdf+xml":      "xml",
    "application/x-rdf+xml":    "xml",
    "text/xml":                 "xml",
}

#: Tiling-related MIME content-type substrings used as a fallback heuristic
#: when the item type cannot be determined from the public C API alone.
_TILING_HINTS: dict[str, str] = {
    "grid":        "grid",
    "tili":        "tili",
    "unci":        "unci",
    "uncompressed": "unci",
}


class HeifContext:
    """Wrapper around a ``heif_context*``.

    Load a file with :py:meth:`from_file` and use as a context manager::

        with HeifContext.from_file("image.heif") as ctx:
            ids = ctx.top_level_image_ids()
    """

    def __init__(self) -> None:
        if not SWIG_BINDING_AVAILABLE:
            raise RuntimeError(
                "libheif_binding SWIG extension not compiled.\n"
                "Run:  cd libheif_binding && ./build.sh"
            )
        self._ctx = _lib.heif_context_alloc()
        if not self._ctx:
            raise RuntimeError("heif_context_alloc() returned NULL")

    # ── Factory ───────────────────────────────────────────────────────
    @classmethod
    def from_file(cls, path: str) -> "HeifContext":
        """Allocate a context and load *path*.

        Raises :py:class:`HeifError` if the file cannot be opened or is not
        a valid HEIF/AVIF/HEIC container.
        """
        obj = cls()
        err = _lib.heif_context_read_from_file(obj._ctx, path.encode(), None)
        _check(err)
        return obj

    # ── Context-manager protocol ───────────────────────────────────────
    def __enter__(self) -> "HeifContext":
        return self

    def __exit__(self, *_: object) -> None:
        self.free()

    def free(self) -> None:
        """Explicitly free the underlying ``heif_context*``."""
        if self._ctx is not None:
            _lib.heif_context_free(self._ctx)
            self._ctx = None

    # ── Image enumeration ─────────────────────────────────────────────
    def top_level_image_ids(self) -> list[int]:
        """Return the list of top-level image item IDs in the file."""
        return _lib.heif_get_top_level_image_ids(self._ctx)

    def get_image_handle(self, image_id: int) -> ImageHandle:
        """Return an :py:class:`ImageHandle` for *image_id*.

        The caller is responsible for releasing it (use as a context manager).
        Raises :py:class:`HeifError` on failure.
        """
        err, handle_ptr = _lib.heif_context_get_image_handle(self._ctx, image_id)
        _check(err)
        return ImageHandle(handle_ptr)

    # ── High-level helpers ────────────────────────────────────────────
    def detect_tiling_mode(self) -> str | None:
        """Detect the tiling mode of the primary image.

        Returns ``'grid'``, ``'tili'``, ``'unci'``, or ``None`` for non-tiled
        images.

        Implementation notes
        --------------------
        The definitive detection requires ``heif_image_handle_get_item_type()``
        which distinguishes the 4-byte ISOBMFF box type (grid / tili / unci)
        but is not yet in libheif's stable public header.  Until it is, this
        method uses two signals available from the current public API:

        1. **Tile count** (libheif ≥ 1.17): a non-zero tile count confirms
           the image IS tiled but does not tell us the box type.
        2. **Metadata content-type hints**: applications may embed a 'mime'
           metadata block whose content_type contains 'grid', 'tili', or 'unci'.

        If neither signal resolves the type, this method returns ``'grid'`` as
        the safest assumption when tiles are present (grid is the most common
        and best-supported mode).
        TODO: add ``heif_image_handle_get_item_type()`` to the SWIG interface
        once libheif exposes it publicly; that call gives a definitive answer.
        """
        for image_id in self.top_level_image_ids():
            with self.get_image_handle(image_id) as handle:
                # Signal 1: metadata content-type hints
                for block in handle.metadata_blocks():
                    ct = block.content_type.lower()
                    for hint, mode in _TILING_HINTS.items():
                        if hint in ct:
                            return mode

                # Signal 2: non-zero tile count (requires libheif ≥ 1.17)
                try:
                    n = handle.tile_count
                    if n > 0:
                        # Type unknown from public API; 'grid' is the safe default.
                        return "grid"
                except Exception:
                    pass

        return None

    def find_rdf_metadata(self) -> tuple[bytes | None, str | None]:
        """Search all top-level image items for embedded RDF/TTL metadata.

        Iterates metadata blocks via the libheif C API and inspects their
        MIME content-type.  This is the clean, authoritative replacement for
        the byte-scan approach previously used in ``has_internal_rdf()`` and
        ``extract_internal_rdf()``.

        Returns:
            ``(data_bytes, format)`` where format is ``'turtle'`` or ``'xml'``,
            or ``(None, None)`` if no RDF metadata is found.
        """
        for image_id in self.top_level_image_ids():
            with self.get_image_handle(image_id) as handle:
                for block in handle.metadata_blocks():
                    fmt = _RDF_CONTENT_TYPES.get(block.content_type)
                    if fmt:
                        data = block.read()
                        if data:
                            return data, fmt
        return None, None
