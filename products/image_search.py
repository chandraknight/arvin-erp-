"""
Perceptual hash image search using only Pillow (no extra deps).
Algorithm: 8x8 average hash — fast, good enough for product matching.
"""
from PIL import Image


def compute_phash(image_file) -> str:
    img = Image.open(image_file).convert('L').resize((8, 8), Image.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / 64
    bits = ''.join('1' if p >= avg else '0' for p in pixels)
    return format(int(bits, 2), '016x')


def hamming_distance(a: str, b: str) -> int:
    if not a or not b:
        return 64
    try:
        return bin(int(a, 16) ^ int(b, 16)).count('1')
    except ValueError:
        return 64


def search_by_image(image_file, company, max_distance: int = 20):
    from apps.products.models import ProductImage
    query_hash = compute_phash(image_file)
    candidates = (
        ProductImage.objects
        .filter(product__company=company, product__is_active=True)
        .select_related('product')
        .exclude(image_hash='')
    )
    results = []
    seen_product_ids = set()
    for pi in candidates:
        dist = hamming_distance(query_hash, pi.image_hash)
        if dist <= max_distance and pi.product_id not in seen_product_ids:
            results.append((dist, pi.product))
            seen_product_ids.add(pi.product_id)

    results.sort(key=lambda x: x[0])
    return [p for _, p in results]
