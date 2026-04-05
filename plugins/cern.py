from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

import requests
from PIL import Image

from common import turbo56k as TT
from common.bbsdebug import _LOG, bcolors
from common.filetools import SendBitmap
from common.imgcvt import GFX_MODES, PreProcess, dithertype, gfxmodes

if TYPE_CHECKING:
    from common.connection import Connection


DASHBOARD_URL = 'https://vistar-capture.s3.cern.ch/lhc1.png'
PANEL_ORDER = ('Intensity', 'Luminosity', 'Status', 'BIS')


@dataclass
class Slide:
    title: str
    image: Image.Image


###############
# Plugin setup
###############
def setup():
    fname = "CERN"  # UPPERCASE function name for config.ini
    parpairs = []   # config.ini Parameter pairs (name,defaultvalue)
    return (fname, parpairs)


def _supports_graphics(conn: Connection) -> bool:
    return conn.QueryFeature(TT.PRADDR) < 0x80 or (conn.T56KVer == 0 and len(conn.encoder.gfxmodes) > 0)


def _choose_gfxmode(conn: Connection):
    if 'PET64' in conn.mode:
        return gfxmodes.C64HI
    if conn.mode == 'PET264':
        return gfxmodes.P4HI
    if conn.mode == 'MSX1':
        return gfxmodes.MSXSC2
    if conn.mode == 'ZX1':
        return gfxmodes.ZXHI
    if conn.encoder.def_gfxmode is not None:
        return conn.encoder.def_gfxmode
    if len(conn.encoder.gfxmodes) > 0:
        return conn.encoder.gfxmodes[0]
    return None


def _fetch_dashboard() -> Image.Image:
    headers = {'User-Agent': 'RetroBBS-CERN/1.0'}
    response = requests.get(DASHBOARD_URL, timeout=12, headers=headers)
    response.raise_for_status()
    img = Image.open(BytesIO(response.content))
    return img.convert('RGB')


def _panel_boxes(width: int, height: int):
    if height >= 531:
        margin_x = 13 if width >= 64 else max(2, round(width * 0.0125))
        charts_top = 240
        charts_bottom = min(height, 515)
        lower_top = 530
    else:
        margin_x = max(2, round(width * 0.0125))
        charts_top = max(0, round(height * 0.403))
        charts_bottom = min(height, round(height * 0.866))
        lower_top = min(height, round(height * 0.891))
    half_width = width // 2

    return {
        'Intensity': (margin_x, charts_top, half_width, charts_bottom),
        'Luminosity': (half_width, charts_top, width - margin_x, charts_bottom),
        'Status': (0, lower_top, half_width, height),
        'BIS': (half_width, lower_top, width, height),
    }


def _crop_box(box, width: int, height: int):
    left, top, right, bottom = box
    left = max(0, min(width - 1, int(left)))
    top = max(0, min(height - 1, int(top)))
    right = max(left + 1, min(width, int(right)))
    bottom = max(top + 1, min(height, int(bottom)))
    return (left, top, right, bottom)


def _resize_panel(panel: Image.Image, gfxmode) -> Image.Image:
    target_size = GFX_MODES[gfxmode]['in_size']
    if panel.size == target_size:
        return panel.copy()
    return panel.resize(target_size, Image.LANCZOS)


def _build_slides(source: Image.Image, gfxmode):
    width, height = source.size
    if width < 64 or height < 64:
        return [Slide('Dashboard', _resize_panel(source, gfxmode))]

    boxes = _panel_boxes(width, height)
    slides = []
    for title in PANEL_ORDER:
        panel = source.crop(_crop_box(boxes[title], width, height))
        if panel.getbbox() is None:
            continue
        slides.append(Slide(title, _resize_panel(panel, gfxmode)))
    return slides


def _show_slide(conn: Connection, slide: Slide, gfxmode):
    if not _supports_graphics(conn) or gfxmode is None:
        return False

    return SendBitmap(
        conn,
        slide.image,
        gfxmode=gfxmode,
        preproc=PreProcess(brightness=1.0, contrast=1.5, saturation=1.15, sharpness=1.2),
        dither=dithertype.NONE,
    ) is not False


def _close_slides(slides):
    for slide in slides:
        try:
            slide.image.close()
        except Exception:
            ...


##################################################
# Plugin function
##################################################
def plugFunction(conn: Connection):
    back = conn.encoder.back
    next_keys = [' ', conn.encoder.nl]
    gfxmode = _choose_gfxmode(conn)
    slides = []
    slide_index = 0

    try:
        source = None
        try:
            source = _fetch_dashboard()
            slides = _build_slides(source, gfxmode)
            _LOG('CERN - dashboard updated', id=conn.id, v=4)
        except Exception as exc:
            _LOG(bcolors.WARNING + f'CERN - {exc}' + bcolors.ENDC, id=conn.id, v=2)
            conn.SendTML('<BR><RED>Unable to load CERN dashboard.<PAUSE n=2>')
            return False
        finally:
            if source is not None:
                source.close()

        if len(slides) == 0:
            conn.SendTML('<BR><RED>No CERN panels available.<PAUSE n=2>')
            return False

        if not _supports_graphics(conn) or gfxmode is None:
            conn.SendTML('<BR><ORANGE>CERN requires a graphics-capable terminal.<PAUSE n=2>')
            return False

        while conn.connected:
            slide = slides[slide_index]
            if _show_slide(conn, slide, gfxmode) is False:
                break

            key = conn.ReceiveKey(next_keys + [back])
            if not conn.connected or key == back:
                break

            slide_index = (slide_index + 1) % len(slides)
    finally:
        _close_slides(slides)
        conn.SendTML(f'<NUL n=2><TEXT page=0 border={conn.style.BoColor} background={conn.style.BgColor}><CURSOR>')
