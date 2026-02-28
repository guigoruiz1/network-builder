import os
import re
import asyncio
from PIL import Image
import requests
from io import BytesIO
import glob

# --- Filename sanitization utility ---

sizes = {
    "ref": (690, 1000),
    "offset": (82, 182),
    "crop": (528, 522),
}


def filename(name, ext=None):
    """
    Sanitize a card name for use as a filename by removing all non-alphanumeric characters.

    Args:
        name (str): Card name to sanitize.
        ext (str or list or None): Extension to use. If None, try to detect an existing
            file among common extensions and return that path; if none exist, default to 'jpg'.
    Returns:
        str: Path to the filename with the chosen or detected extension.
    """
    base = f"images/{re.sub(r'[^\w]', '', name)}"

    def path_for(e):
        return f"{base}.{e}"

    pref_exts = ["jpg", "jpeg", "png", "svg"]

    # If ext explicitly provided as list/tuple, prefer existing files in that order
    if isinstance(ext, (list, tuple)):
        for e in ext:
            p = path_for(e)
            if os.path.isfile(p):
                return p
        # fall back to any match
        matches = glob.glob(f"{base}.*")
        if matches:
            return matches[0]
        return path_for(ext[0])

    # If ext explicitly provided as string, return that path
    if isinstance(ext, str):
        return path_for(ext)

    # ext is None -> use glob to find any existing file
    matches = glob.glob(f"{base}.*")
    if matches:
        # prefer known extensions order
        for e in pref_exts:
            for m in matches:
                if m.lower().endswith(f".{e}"):
                    return m
        return matches[0]

    # default
    return path_for("jpg")


# --- Image downloading and cropping utilities ---


def _crop_section(
    im,
    *,
    out_size=None,
):
    """
    Crop a PIL image to the configured section and optionally resize.

    Args:
        im (PIL.Image): Image to crop.
        out_size (tuple or None): Optional output size (width, height).
    Returns:
        PIL.Image: Cropped and optionally resized image.
    """
    w, h = im.size
    ref_w, ref_h = sizes["ref"]
    ref_aspect = ref_w / ref_h
    aspect = w / h
    if abs(aspect - ref_aspect) > 1e-6:
        if aspect > ref_aspect:
            # image is wider -> crop width
            new_w = int(round(h * ref_aspect))
            new_w = min(new_w, w)
            left = max(0, (w - new_w) // 2)
            right = left + new_w
            im = im.crop((left, 0, right, h))
        else:
            # image is taller -> crop height
            new_h = int(round(w / ref_aspect))
            new_h = min(new_h, h)
            top = max(0, (h - new_h) // 2)
            bottom = top + new_h
            im = im.crop((0, top, w, bottom))
        w, h = im.size

    ox = sizes["offset"][0] / ref_w
    oy = sizes["offset"][1] / ref_h
    cw = sizes["crop"][0] / ref_w
    ch = sizes["crop"][1] / ref_h

    left = int(round(ox * w))
    top = int(round(oy * h))
    right = left + int(round(cw * w))
    bottom = top + int(round(ch * h))

    # Clamp to image bounds and shift if necessary
    if right > w:
        right = w
        left = max(0, w - int(round(cw * w)))
    if bottom > h:
        bottom = h
        top = max(0, h - int(round(ch * h)))

    cropped = im.crop((left, top, right, bottom))
    if out_size:
        resampling = Image.Resampling.LANCZOS
        cropped = cropped.resize(out_size, resampling)

    return cropped


def _download_images_fallback(names):
    """
    Download and crop card images directly from Yugipedia API (fallback method).
    Used when yugiquery utilities are unavailable. Saves images to images/<Card_Name>.jpg.
    Skips existing files.

    Args:
        names (Iterable[str]): Card names to download.
    """
    image_dir = "images"
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    }
    base_url = "https://yugipedia.com/api.php"

    def fetch_image(image_title):
        params = {
            "action": "query",
            "format": "json",
            "titles": f"File:{image_title}",
            "prop": "imageinfo",
            "iiprop": "url",
        }
        try:
            resp = session.get(base_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            image_url = None
            for page in pages.values():
                imageinfo = page.get("imageinfo")
                if imageinfo and isinstance(imageinfo, list) and "url" in imageinfo[0]:
                    image_url = imageinfo[0]["url"]
            if image_url:
                ext = image_title.split(".")[-1].lower()
                img_resp = session.get(image_url, headers=headers, timeout=10)
                img_resp.raise_for_status()
                img_bytes = BytesIO(img_resp.content)
                if ext == "svg":
                    return img_bytes
                else:
                    try:
                        img = Image.open(img_bytes)
                        return img
                    except Exception:
                        return None
            else:
                return None
        except Exception:
            return None

    for name in sorted(names):
        existing = filename(name, ext=None)
        if os.path.exists(existing):
            continue

        sanitized = re.sub(r"[\W]", "", name)
        found = False
        for image_title in [
            f"{sanitized}-MADU-EN-VG-artwork.png",
            f"{sanitized}-OW.png",
            f"{sanitized}.svg",
        ]:
            ext = image_title.split(".")[-1].lower()
            img_obj = fetch_image(image_title)
            if img_obj is not None:
                file_path = filename(name, ext=ext)
                if ext == "svg" and isinstance(img_obj, BytesIO):
                    with open(file_path, "wb") as f:
                        f.write(img_obj.getvalue())
                elif isinstance(img_obj, Image.Image):
                    img_obj.save(file_path)
                found = True
                break

        if not found:
            # Fallback to featured image via API (with cropping)
            params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "titles": name,
                "piprop": "original",
            }
            try:
                resp = session.get(base_url, params=params, headers=headers, timeout=10)
                resp.raise_for_status()
                data_json = resp.json()
                pages = data_json.get("query", {}).get("pages", {})
                image_url = None
                for page in pages.values():
                    original = page.get("original")
                    thumbnail = page.get("thumbnail")
                    if original and "source" in original:
                        image_url = original["source"]
                    elif thumbnail and "original" in thumbnail:
                        image_url = thumbnail["original"]
                if not image_url:
                    print(f"[WARN] No image found for '{name}'")
                    continue
                img_resp = session.get(image_url, headers=headers, timeout=10)
                img_resp.raise_for_status()
                img_bytes = BytesIO(img_resp.content)
                if (
                    image_url.lower().endswith(".svg")
                    or img_resp.headers.get("Content-Type", "").lower()
                    == "image/svg+xml"
                ):
                    file_path = filename(name, ext="svg")
                    with open(file_path, "wb") as f:
                        f.write(img_bytes.getvalue())
                    continue
                else:
                    file_path = filename(name, ext="jpg")
                    img = Image.open(img_bytes)
                    img = _crop_section(img, out_size=None)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(file_path)
            except Exception as e:
                print(f"[ERROR] Failed to download image for '{name}': {e}")


def download(names, config):
    """
    Download and crop card images from Yugipedia.
    Attempts yugiquery utilities first (async + featured images), falls back to direct API.
    Saves images to images/<Card_Name>.jpg. Skips existing files.

    Args:
        names (Iterable[str]): Card names to download.
        config (Config): Configuration object for cropping.
    """
    if "sizes" in config and isinstance(config["sizes"], dict):
        global sizes
        for key in config["sizes"]:
            if key in sizes:
                sizes[key] = config["sizes"][key]

    # Try to use yugiquery
    try:
        from yugiquery.utils.api import fetch_featured_images, download_media
        from yugiquery.utils.image import crop_section as yugiquery_crop

        # Fetch the featured image filenames
        file_names = fetch_featured_images(*names)
        image_dir = "images"

        # Download them (only if we got filenames)
        if file_names:
            results = asyncio.run(download_media(*file_names, output_path=image_dir))

            # Print download results
            if results is not None and len(results) > 0:
                succeeded = [
                    r
                    for r in results
                    if isinstance(r, dict) and r.get("status") == "success"
                ]
                failed = [
                    r
                    for r in results
                    if isinstance(r, dict) and r.get("status") == "failed"
                ]
                print(
                    f"Downloaded {len(succeeded)}/{len(results)} images using yugiquery"
                )
                if failed:
                    for result in failed:
                        print(f"[WARN] Failed to download: {result.get('file_name')}")

            # Crop the downloaded images
            for name in names:
                file_path = filename(name)
                if os.path.exists(file_path):
                    try:
                        with Image.open(file_path) as img:
                            cropped_img = yugiquery_crop(
                                img,
                                ref=sizes["ref"],
                                offset=sizes["offset"],
                                crop_size=sizes["crop"],
                                out_size=None,
                            )
                            cropped_img.save(file_path)
                    except Exception as e:
                        print(f"[WARN] Failed to crop image for '{name}': {e}")
        else:
            print("[WARN] No image filenames found")
    except:
        print(
            "[WARN] yugiquery utilities unavailable, falling back to direct API method"
        )
        _download_images_fallback(names)
