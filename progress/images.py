"""Image handling for client-uploaded progress photos.

Clients shoot these on a phone: 3–12MB, 4000px wide, and frequently stored
sideways with the real orientation only in an EXIF tag. Serving those raw would
waste the coach's mobile data and render half the photos rotated. Everything is
normalised once, at upload.
"""

from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

#: Longest edge we keep. The comparison view shows these a few hundred px wide;
#: 1600 leaves room to zoom in on detail without storing a 12MB original.
MAX_EDGE_PX = 1600

#: Reject before decoding: a 25MB upload is a mistake or an attack, not a photo.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

JPEG_QUALITY = 82


class ImageRejected(Exception):
    """Raised with a message suitable for showing to the person uploading."""


def process_upload(uploaded, max_edge=MAX_EDGE_PX):
    """Validate, EXIF-rotate and downscale an uploaded image.

    Returns a Django file ready to assign to an ImageField. Raises
    ``ImageRejected`` with a plain-language reason if the file is unusable, so
    the form can surface it rather than throwing a 500.

    Photos already smaller than ``max_edge`` are still re-encoded: it strips
    EXIF (which carries GPS coordinates on most phones) and applies the rotation
    permanently. Losing location metadata from a physique photo is a feature.
    """
    if uploaded is None:
        return None

    size = getattr(uploaded, "size", None)
    if size and size > MAX_UPLOAD_BYTES:
        raise ImageRejected(
            _("That image is %(size)s MB. Please keep photos under %(limit)s MB.")
            % {
                "size": round(size / 1024 / 1024, 1),
                "limit": MAX_UPLOAD_BYTES // 1024 // 1024,
            }
        )

    try:
        uploaded.seek(0)
        image = Image.open(uploaded)
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageRejected(_("That file isn't an image we can read.")) from None

    # Bake the EXIF orientation into the pixels, then drop the metadata.
    image = ImageOps.exif_transpose(image)

    # JPEG has no alpha channel; flatten anything that does onto white.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.split()[-1])
        image = flat
    elif image.mode != "RGB":
        image = image.convert("RGB")

    if max(image.size) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    buffer.seek(0)

    stem = (getattr(uploaded, "name", "photo") or "photo").rsplit(".", 1)[0]
    # Strip any path components a browser may have included.
    stem = stem.replace("\\", "/").rsplit("/", 1)[-1][:60] or "photo"

    return InMemoryUploadedFile(
        buffer,
        field_name=None,
        name=f"{stem}.jpg",
        content_type="image/jpeg",
        size=buffer.getbuffer().nbytes,
        charset=None,
    )
