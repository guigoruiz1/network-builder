import os
import re
import asyncio
from PIL import Image
import requests
from io import BytesIO
import glob
import hashlib
from tqdm.auto import tqdm

# --- Global parameters ---

sizes = {
    "ref": (690, 1000),
    "offset": (82, 182),
    "crop": (528, 522),
}

base_path = "images"
patterns = [
    "{name}-MADU-EN-VG-artwork.png",
    "{name}-OW.png",
    "{name}.svg",
]

# --- Mandatory functions for network script ---


def download(names, config):
    """
    Function to download images. The user is free to implement this as they see fit.
    The saved images should be named in a way that is consistent with the return value of `filename(name)`.
    In this example, we download YU-GI-OH card images.

    Args:
        names (Iterable[str]): Node names for which to download images.
        config (Any): Optional configuration object with user-defined parameters from the calling context.

    returns:
        None
    """

    if "images" in config and isinstance(config["images"], dict):
        if "sizes" in config["images"] and isinstance(config["images"]["sizes"], dict):
            global sizes
            for key in config["images"]["sizes"]:
                if key in sizes:
                    sizes[key] = config["images"]["sizes"][key]
        if "base_path" in config["images"] and isinstance(
            config["images"]["base_path"], str
        ):
            global base_path
            base_path = config["images"]["base_path"]

    if not os.path.exists(base_path):
        os.makedirs(base_path)

    # Try to use yugiquery
    try:
        _download_images_yugiquery(names)
    except:
        print(
            "[WARN] yugiquery utilities unavailable, falling back to direct API method"
        )
        _download_images_fallback(names)


def filename(name, ext=None):
    """
    Converts a passed name into a filename path.
    Must be consistent with the naming scheme used in `download()`.
    Returns None if no file exists.

    Args:
        name (str): Card name.
        ext (str, optional): File extension.
            - If None: returns existing file path or None
            - If "": returns just the sanitized name (no path, no ext)
            - Otherwise: returns path with that extension

    Returns:
        str or None: File path, sanitized name, or None if file doesn't exist.
    """
    sanitized = re.sub(r"[^\w]", "", name)
    base = os.path.join(base_path, sanitized)

    # Return just the sanitized name (no path)
    if ext == "":
        return sanitized

    # Specific extension requested
    if ext is not None:
        return f"{base}.{ext}"

    # No extension specified - look for existing file
    pref_exts = ["jpg", "jpeg", "png", "svg"]
    matches = glob.glob(f"{base}.*")
    if matches:
        for e in pref_exts:
            for m in matches:
                if m.lower().endswith(f".{e}"):
                    return m
        return matches[0]

    return None


# --- Internal functions ---


def _save_image(img_obj, name, ext):
    file_path = filename(name, ext=ext)
    if ext == "svg" and isinstance(img_obj, BytesIO):
        with open(file_path, "wb") as f:
            f.write(img_obj.getvalue())
    elif isinstance(img_obj, Image.Image):
        img_obj.save(file_path)
    else:
        print(f"[WARN] Unrecognized image object for '{name}'")


def _move_download(result, card_name):
    """
    Move a successfully downloaded file to the path expected by filename().

    Args:
        result (dict): A download_media result dict with keys "file_name" and "success".
        card_name (str): The card name used to derive the destination path.
    """
    src = os.path.join(base_path, result["file_name"])
    ext = result["file_name"].split(".")[-1]
    dst = filename(card_name, ext=ext)
    if src != dst and os.path.exists(src):
        try:
            os.rename(src, dst)
        except OSError as e:
            print(f"[WARN] Could not rename '{src}' to '{dst}': {e}")


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


def _fetch_image(image_url, session, headers):
    """
    Try to fetch an image from Yugipedia's static file server using the MD5 hash path.
    Returns a PIL Image or BytesIO (for SVG) or None.
    """
    ext = image_url.split(".")[-1].lower()
    try:
        img_resp = session.get(image_url, headers=headers, timeout=10)
        if img_resp.status_code != 200:
            return None
        img_bytes = BytesIO(img_resp.content)
        if ext == "svg":
            return img_bytes
        else:
            try:
                img = Image.open(img_bytes)
                return img
            except Exception:
                return None
    except Exception:
        return None


def _fetch_featured_image(card_name, session, headers, base_url):
    """
    Query the card page for the featured image using the MediaWiki API.
    Returns a PIL Image or BytesIO (for SVG) or None.
    """
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "titles": card_name,
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
        return image_url
    except Exception:
        return None


def _download_images_fallback(names):
    """
    Download and crop card images directly from Yugipedia (fallback method).
    Tries static file server first, then queries card page for featured image.
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    }
    base_url = "https://yugipedia.com/api.php"

    for name in tqdm(sorted(names)):
        existing = filename(name)
        if existing and os.path.exists(existing):
            continue

        sanitized = filename(name, "")
        found = False
        for pattern in patterns:
            image_title = pattern.format(name=sanitized)
            md5 = hashlib.md5(image_title.encode("utf-8")).hexdigest()
            image_url = f"https://ms.yugipedia.com//{md5[0]}/{md5[0:2]}/{image_title}"
            img_obj = _fetch_image(image_url, session, headers)
            if img_obj is not None:
                ext = image_title.split(".")[-1].lower()
                _save_image(img_obj, sanitized, ext)
                found = True
                break

        if not found:
            image_url = _fetch_featured_image(name, session, headers, base_url)
            if image_url:
                img_obj = _fetch_image(image_url, session, headers)
                img_obj = _crop_section(img_obj, out_size=None)
                if img_obj is not None:
                    ext = image_url.split(".")[-1].lower()
                    _save_image(img_obj, sanitized, ext)
            else:
                print(f"[WARN] No image found for '{name}'")


# --- Optional utility functions for yugiquery-based downloading ---


def _download_images_yugiquery(names):
    """
    Download and crop card images using yugiquery utilities (async + featured images).
    Saves images to images/<Card_Name>.<ext>. Skips existing files.
    Processes files pattern by pattern, prioritizing specific naming patterns
    and retrying downloads for failed files with the next pattern sequentially.

    Args:
        names (Iterable[str]): Card names to download.
    """
    from yugiquery.utils.media import fetch_page_images, download_media

    remaining = [name for name in names if filename(name) is None]

    for pattern in patterns:
        if not remaining:
            break

        file_names = [pattern.format(name=filename(n, "")) for n in remaining]

        # Download all files for this pattern in one call
        results = asyncio.run(download_media(*file_names, output_path=base_path))

        succeeded = set()
        if results:
            for name, result in zip(remaining, results):
                if isinstance(result, dict) and result.get("success"):
                    _move_download(result, name)
                    succeeded.add(name)

        print(f"Downloaded {len(succeeded)}/{len(remaining)} using pattern {pattern}")
        remaining = [n for n in remaining if n not in succeeded]

    # Fallback to featured images
    if remaining:
        image_dict = fetch_page_images(*remaining, featured=True)
        if image_dict:
            # Create reverse mapping: filename -> card_name
            filename_to_card = {fname: cname for cname, fname in image_dict.items()}

            results = asyncio.run(
                download_media(*list(image_dict.values()), output_path=base_path)
            )

            succeeded_count = 0
            if results:
                for result in results:
                    if isinstance(result, dict) and result.get("success"):
                        card_name = filename_to_card.get(result["file_name"])
                        if card_name:
                            _move_download(result, card_name)
                            file_path = filename(card_name)
                            if file_path and os.path.exists(file_path):
                                try:
                                    with Image.open(file_path) as img:
                                        _crop_section(img).save(file_path)
                                except Exception as e:
                                    print(f"[WARN] Failed to crop '{card_name}': {e}")
                            succeeded_count += 1

            print(
                f"Downloaded {succeeded_count}/{len(remaining)} using featured images"
            )
            for card_name in remaining:
                if card_name not in filename_to_card:
                    print(f"[WARN] No image found for '{card_name}'")
        else:
            for card_name in remaining:
                print(f"[WARN] No image found for '{card_name}'")
