/* libheif_core.i — SWIG interface for the libheif C API
 *
 * Covers:
 *   - Context management (alloc / free / read_from_file)
 *   - Top-level image enumeration
 *   - Image-handle properties (dimensions, primary flag)
 *   - Metadata-block inspection (type, content-type, raw bytes)
 *   - Image tiling query
 *
 * Build (from this directory):
 *   python setup.py build_ext --inplace
 * or use build.sh.
 *
 * The generated pair (_libheif_core.so + libheif_core.py) can then be
 * imported directly or via the package __init__.py.
 */

%module libheif_core

%{
#define SWIG_FILE_WITH_INIT
#include <stdlib.h>
#include <string.h>
#include "libheif/heif.h"
%}

/* ── Integer / size typedefs ───────────────────────────────────────── */
%include "stdint.i"

typedef unsigned int heif_item_id;

/* ── Error constants (heif_error_code) ─────────────────────────────── */
#define heif_error_Ok                     0
#define heif_error_Input_does_not_exist   1
#define heif_error_Invalid_input          2
#define heif_error_Unsupported_filetype   3
#define heif_error_Unsupported_feature    4
#define heif_error_Usage_error            5
#define heif_error_Memory_allocation_error 6
#define heif_error_Decoder_plugin_error   7
#define heif_error_Encoder_plugin_error   8
#define heif_error_Encoding_error         9

/* ── heif_error struct ──────────────────────────────────────────────── */
struct heif_error {
    int code;
    int subcode;
    const char *message;
};

/* ── Opaque handle structs ──────────────────────────────────────────── */
struct heif_context   {};
struct heif_image_handle {};
struct heif_reading_options {};

/* ── Context management ─────────────────────────────────────────────── */
struct heif_context *heif_context_alloc(void);
void                 heif_context_free(struct heif_context *ctx);

struct heif_error heif_context_read_from_file(
    struct heif_context           *ctx,
    const char                    *filename,
    const struct heif_reading_options *options);

/* ── Top-level images ───────────────────────────────────────────────── */
int heif_context_get_number_of_top_level_images(struct heif_context *ctx);

/* heif_context_get_list_of_top_level_image_IDs: raw form (used by inline helpers) */
int heif_context_get_list_of_top_level_image_IDs(
    struct heif_context *ctx,
    heif_item_id        *IDs,
    int                  count);

/* ── Image handle ───────────────────────────────────────────────────── */

/* OUTPUT typemap: heif_context_get_image_handle writes to heif_image_handle**
 * SWIG will make the function return (heif_error, heif_image_handle*) as a
 * Python tuple.
 */
%typemap(in, numinputs=0)
    struct heif_image_handle **out_handle
    (struct heif_image_handle *_out_tmp = NULL)
{
    $1 = &_out_tmp;
}
%typemap(argout) struct heif_image_handle **out_handle {
    PyObject *_handle_obj = SWIG_NewPointerObj(
        (void *)*$1, SWIGTYPE_p_heif_image_handle, 0 /* caller manages lifetime */);
    $result = SWIG_Python_AppendOutput($result, _handle_obj);
}

struct heif_error heif_context_get_image_handle(
    struct heif_context       *ctx,
    heif_item_id               id,
    struct heif_image_handle **out_handle);

void heif_image_handle_release(const struct heif_image_handle *handle);

int heif_image_handle_get_width(const struct heif_image_handle *handle);
int heif_image_handle_get_height(const struct heif_image_handle *handle);
int heif_image_handle_is_primary_image(const struct heif_image_handle *handle);

/* Item ID of this image handle (useful for correlating with raw item lists) */
heif_item_id heif_image_handle_get_item_id(const struct heif_image_handle *handle);

/* ── Tiling ─────────────────────────────────────────────────────────── */
/*
 * heif_image_handle_get_number_of_tiles() is available in libheif ≥ 1.17.
 * Distinguishing grid / tili / unci by item-type via the public C API
 * requires heif_image_handle_get_item_type(), which is not yet in the
 * stable public header.  TODO: expose it here once libheif adds it to
 * the public API — that will let detect_tiling_mode() remove the remaining
 * byte-scan fallback without ambiguity.
 */
int heif_image_handle_get_number_of_tiles(const struct heif_image_handle *handle);

/* ── Metadata blocks attached to an image handle ────────────────────── */
int heif_image_handle_get_number_of_metadata_blocks(
    const struct heif_image_handle *handle,
    const char                     *type_filter);

int heif_image_handle_get_list_of_metadata_block_IDs(
    const struct heif_image_handle *handle,
    const char                     *type_filter,
    heif_item_id                   *ids,
    int                             count);

const char *heif_image_handle_get_metadata_type(
    const struct heif_image_handle *handle,
    heif_item_id                    metadata_id);

const char *heif_image_handle_get_metadata_content_type(
    const struct heif_image_handle *handle,
    heif_item_id                    metadata_id);

size_t heif_image_handle_get_metadata_size(
    const struct heif_image_handle *handle,
    heif_item_id                    metadata_id);

struct heif_error heif_image_handle_get_metadata(
    const struct heif_image_handle *handle,
    heif_item_id                    metadata_id,
    void                           *out_data);

/* ── Python-friendly inline helpers ─────────────────────────────────── */
/*
 * These helpers wrap the C array-output functions and return Python lists /
 * bytes objects directly, avoiding manual buffer management from Python.
 */
%inline %{

/* Return a Python list of top-level image item IDs (list[int]). */
PyObject *heif_get_top_level_image_ids(struct heif_context *ctx)
{
    int n = heif_context_get_number_of_top_level_images(ctx);
    PyObject *list = PyList_New(0);
    if (n <= 0)
        return list;
    heif_item_id *ids = (heif_item_id *)malloc((size_t)n * sizeof(heif_item_id));
    if (!ids)
        return list;
    heif_context_get_list_of_top_level_image_IDs(ctx, ids, n);
    for (int i = 0; i < n; i++)
        PyList_Append(list, PyLong_FromUnsignedLong((unsigned long)ids[i]));
    free(ids);
    return list;
}

/*
 * Return a Python list of metadata-block IDs (list[int]).
 * Pass type_filter=NULL to get all blocks; pass e.g. "mime" to filter.
 */
PyObject *heif_get_metadata_block_ids(
    const struct heif_image_handle *handle,
    const char                     *type_filter)
{
    int n = heif_image_handle_get_number_of_metadata_blocks(handle, type_filter);
    PyObject *list = PyList_New(0);
    if (n <= 0)
        return list;
    heif_item_id *ids = (heif_item_id *)malloc((size_t)n * sizeof(heif_item_id));
    if (!ids)
        return list;
    heif_image_handle_get_list_of_metadata_block_IDs(handle, type_filter, ids, n);
    for (int i = 0; i < n; i++)
        PyList_Append(list, PyLong_FromUnsignedLong((unsigned long)ids[i]));
    free(ids);
    return list;
}

/*
 * Read the content of a metadata block and return it as Python bytes,
 * or None if the block is empty or an error occurs.
 */
PyObject *heif_get_metadata_bytes(
    const struct heif_image_handle *handle,
    heif_item_id                    metadata_id)
{
    size_t sz = heif_image_handle_get_metadata_size(handle, metadata_id);
    if (sz == 0)
        Py_RETURN_NONE;
    void *buf = malloc(sz);
    if (!buf)
        Py_RETURN_NONE;
    struct heif_error err = heif_image_handle_get_metadata(handle, metadata_id, buf);
    if (err.code != 0) {
        free(buf);
        Py_RETURN_NONE;
    }
    PyObject *result = PyBytes_FromStringAndSize((const char *)buf, (Py_ssize_t)sz);
    free(buf);
    return result;
}

%}
