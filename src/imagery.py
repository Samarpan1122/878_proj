"""NAIP aerial imagery features per location (Microsoft Planetary Computer, public domain).

For each location: a CHIP x CHIP pixel window (0.6 m NAIP => ~134 m) centered on the point.
  - spectral "segmentation" fractions from NDVI (RGB+NIR): veg, impervious, water
  - 512-d ImageNet ResNet-18 embedding of the RGB chip
Raw chips are never written to disk; only derived features are kept.
# ponytail: ImageNet ResNet-18 + NDVI thresholds stand in for OpenGeoAI segmentation/foundation
#           embeddings (the `geoai` package and its models don't fit on this disk). Swap in
#           geoai / torchgeo weights in `embed()` when there is room.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
import torch
import torchvision
from pyproj import Transformer
from rasterio.windows import Window
from shapely.geometry import Point, shape

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
CHIP = 224
THREADS = 12
NDVI_VEG, NDVI_IMPERVIOUS, NDVI_WATER = 0.3, 0.1, -0.05
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def _latest_items(locs: pd.DataFrame) -> list:
    """Latest NAIP item covering each location (one STAC search over the bbox)."""
    cat = pystac_client.Client.open(STAC)
    bbox = [locs.lng.min(), locs.lat.min(), locs.lng.max(), locs.lat.max()]
    items = sorted(cat.search(collections=["naip"], bbox=bbox).items(), key=lambda i: i.datetime, reverse=True)
    shapes = [(it, shape(it.geometry)) for it in items]
    return [next((it for it, s in shapes if s.contains(Point(x, y))), None) for x, y in zip(locs.lng, locs.lat)]


def _read_item(item, sub: pd.DataFrame) -> list[tuple[int, np.ndarray]]:
    """Read all chips for locations covered by one NAIP item from a single open COG."""
    href = planetary_computer.sign(item.assets["image"].href)
    out = []
    with rasterio.open(href) as src:
        to_img = Transformer.from_crs(4326, src.crs, always_xy=True)
        for loc_id, lng, lat in sub[["loc_id", "lng", "lat"]].itertuples(index=False):
            r, c = src.index(*to_img.transform(lng, lat))
            chip = src.read(window=Window(c - CHIP // 2, r - CHIP // 2, CHIP, CHIP), boundless=True, fill_value=0)
            out.append((loc_id, chip))
    return out


def spectral(chip: np.ndarray) -> dict:
    """NDVI-threshold land-cover fractions from a (4, H, W) RGBN chip."""
    red, nir = chip[0].astype(float), chip[3].astype(float)
    valid = chip.sum(0) > 0
    ndvi = np.where(valid, (nir - red) / (nir + red + 1e-6), np.nan)
    n = max(valid.sum(), 1)
    return {"img_veg_frac": np.nansum(ndvi > NDVI_VEG) / n,
            "img_impervious_frac": np.nansum((ndvi < NDVI_IMPERVIOUS) & (ndvi >= NDVI_WATER)) / n,
            "img_water_frac": np.nansum(ndvi < NDVI_WATER) / n,
            "img_ndvi_mean": np.nanmean(ndvi), "img_ndvi_std": np.nanstd(ndvi),
            "img_brightness": chip[:3][:, valid].mean() / 255 if valid.any() else np.nan}


def embed(chips: list[np.ndarray], batch: int = 128) -> np.ndarray:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    net = torchvision.models.resnet18(weights="IMAGENET1K_V1")
    net.fc = torch.nn.Identity()
    net = net.eval().to(device)
    out = []
    with torch.no_grad():
        for i in range(0, len(chips), batch):
            x = torch.from_numpy(np.stack([c[:3] for c in chips[i:i + batch]])).float() / 255
            out.append(net(((x - IMAGENET_MEAN) / IMAGENET_STD).to(device)).cpu().numpy())
    return np.concatenate(out).astype(np.float32)


def image_features(locs: pd.DataFrame) -> pd.DataFrame:
    items = _latest_items(locs)
    locs = locs.assign(item=[it.id if it else None for it in items])
    by_id = {it.id: it for it in items if it}
    groups = [(by_id[i], sub) for i, sub in locs.dropna(subset=["item"]).groupby("item")]
    print(f"NAIP: {len(locs):,} locations across {len(groups)} image tiles", flush=True)
    with ThreadPoolExecutor(THREADS) as pool:
        chips = [c for part in pool.map(lambda g: _read_item(*g), groups) for c in part]
    ids = [i for i, _ in chips]
    feats = pd.DataFrame([spectral(c) for _, c in chips])
    emb = pd.DataFrame(embed([c for _, c in chips]), columns=[f"emb_{k}" for k in range(512)])
    year = locs.set_index("loc_id").loc[ids, "item"].map(lambda i: by_id[i].datetime.year).to_numpy()
    return pd.concat([pd.DataFrame({"loc_id": ids, "naip_year": year}), feats, emb], axis=1)


IMG_SCALARS = ["img_veg_frac", "img_impervious_frac", "img_water_frac", "img_ndvi_mean", "img_ndvi_std", "img_brightness"]
