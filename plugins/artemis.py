################################################################
# Artemis Mission Control plugin for RetroBBS                  #
# Split-screen telemetry + orbit map tailored for RetroTerm    #
################################################################

import math
import re
import select
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

from common import filetools as FT
from common import turbo56k as TT
from common.bbsdebug import _LOG, bcolors
from common.connection import Connection
from common.imgcvt import GFX_MODES, PreProcess, dithertype, gfxmodes
from common.style import RenderMenuTitle

DEFAULT_URL = 'https://artemis-1bq.pages.dev/'
AUTO_REFRESH_SECONDS = 60
HEADERS = {
    'User-Agent': 'RetroBBS/0.60 Artemis plugin'
}

EARTH_CENTER = {'x': 120.0, 'y': 140.0}
MOON_CENTER = {'x': 880.0, 'y': 140.0}
MOON_ENTRY_ANGLE = -0.65 * math.pi
MOON_EXIT_ANGLE = 0.65 * math.pi

TRAJECTORY_SEGMENTS = [
    ('leo', 0.0, 2.0, 40),
    ('heo', 2.0, 25.5, 80),
    ('trans_lunar', 25.5, 115.0, 60),
    ('flyby', 115.0, 140.0, 40),
    ('trans_earth', 140.0, 209.0, 60),
    ('edl', 209.0, 217.8, 20),
]

FUTURE_ORBIT_COLOR = (96, 96, 96)
PAST_ORBIT_COLOR = (0, 255, 136)

LAUNCH_DATE = datetime.fromisoformat('2026-04-01T22:24:00+00:00')
HEO_PERIOD = 2 * math.pi * math.sqrt(178838122.00405315)
ASCENT_PROFILE = [
    [0, 0, 0, 1.2], [10, 0.3, 50, 1.25], [20, 1.2, 105, 1.35], [30, 2.8, 165, 1.5],
    [40, 5, 230, 1.65], [50, 8, 290, 1.82], [60, 12, 340, 2], [70, 17, 450, 2.1],
    [80, 22, 575, 2.2], [90, 28, 710, 2.3], [100, 34, 860, 2.38], [110, 39, 1020, 2.42],
    [120, 43, 1200, 2.5], [130, 47, 1380, 2.5], [132, 48, 1417, 2.5], [134, 49, 1420, 0.65],
    [140, 52, 1450, 0.68], [160, 63, 1560, 0.75], [180, 76, 1700, 0.82], [191, 88, 1800, 0.85],
    [196, 90, 2030, 0.88], [220, 100, 2650, 1], [260, 115, 3600, 1.4], [300, 126, 4500, 1.8],
    [340, 138, 5500, 2.15], [380, 146, 6300, 2.5], [420, 151, 6950, 2.85], [460, 155, 7450, 3.1],
    [483, 157, 7797, 3.25], [486, 158, 7797, 0], [495, 160, 7797, 0],
]
EDL_PROFILE = [
    [0, 121.9, 11, 0.2], [30, 108, 10.9, 0.5], [60, 92, 10.5, 1.2], [90, 78, 9.5, 2],
    [120, 68, 8, 3], [150, 62, 6.8, 3.8], [180, 61, 5.5, 4], [210, 63, 5, 3.2],
    [240, 68, 4.6, 2], [270, 76, 4.3, 0.8], [300, 80, 4.2, 0.3], [330, 76, 4, 0.6],
    [360, 68, 3.5, 1.5], [400, 55, 2.5, 3.5], [440, 42, 1.5, 4.5], [480, 30, 0.8, 3],
    [520, 20, 0.4, 2], [560, 14, 0.2, 1.5], [600, 9, 0.14, 1.3], [640, 7.6, 0.12, 2.5],
    [680, 4, 0.04, 1.8], [720, 1.5, 0.015, 1.2], [780, 0.2, 0.01, 1], [828, 0, 0.009, 3],
]


def setup():
    fname = 'ARTEMIS'
    parpairs = [('url', DEFAULT_URL)]
    return (fname, parpairs)


def _normalize_lines(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    lines = []
    for raw in soup.get_text('\n').splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if line:
            lines.append(line)
    return lines


def _next_value(lines, label, start=0):
    label_cf = label.casefold()
    for idx in range(start, len(lines)):
        if lines[idx].casefold() == label_cf:
            for j in range(idx + 1, len(lines)):
                if lines[j]:
                    return lines[j], j
    return '', -1


def _extract_data(lines):
    data = {
        'mission_elapsed_time': '',
        'phase': '',
        'flight_day': '',
        'velocity': '',
        'g_force': '',
        'altitude': '',
        'earth_dist': '',
        'moon_dist': '',
    }

    met, met_idx = _next_value(lines, 'Mission Elapsed Time')
    data['mission_elapsed_time'] = met

    if met_idx >= 0:
        for idx in range(met_idx + 1, len(lines)):
            if lines[idx].casefold() == 'flight day':
                break
            data['phase'] = lines[idx]
            break

    data['flight_day'], _ = _next_value(lines, 'Flight Day')
    data['velocity'], _ = _next_value(lines, 'VELOCITY')
    data['g_force'], _ = _next_value(lines, 'G-FORCE')
    data['altitude'], _ = _next_value(lines, 'ALTITUDE')
    data['earth_dist'], _ = _next_value(lines, 'EARTH DIST')
    data['moon_dist'], _ = _next_value(lines, 'MOON DIST')

    if not data['phase']:
        phase, _ = _next_value(lines, 'PHASE')
        data['phase'] = phase

    return data


def _get_artemis_data(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    lines = _normalize_lines(resp.text)
    if not lines:
        raise ValueError('Empty Artemis page')
    data = _extract_data(lines)
    data.update(_compute_live_data())
    return data


def _sanitize_tml(value: str):
    return (value or '').replace('<', '(').replace('>', ')')


def _fit(value: str, width: int):
    value = _sanitize_tml((value or 'N/A').strip())
    if width <= 0:
        return ''
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[:width - 3] + '...'


def _with_unit(value: str, unit: str):
    value = (value or '').strip()
    if not value:
        return 'N/A'
    if unit.casefold() in value.casefold():
        return value
    return f'{value} {unit}'


def _fmt_num_unit(value: str, unit: str, decimals: int = 2):
    value = (value or '').strip()
    if not value:
        return 'N/A'

    cleaned = value.replace(',', '').strip()
    pattern = r'^([-+]?\d+(?:\.\d+)?)(?:\s*([A-Za-z/]+))?$'
    match = re.match(pattern, cleaned)
    if not match:
        return _with_unit(value, unit)

    num = float(match.group(1))
    found_unit = (match.group(2) or '').strip()
    out_unit = found_unit if found_unit else unit
    return f'{num:.{decimals}f} {out_unit}'


def _split_num_unit(value: str):
    value = (value or '').strip()
    if not value:
        return ('N/A', '')
    parts = value.rsplit(' ', 1)
    if len(parts) == 2 and re.search(r'[A-Za-z/]', parts[1]):
        return (parts[0], parts[1])
    return (value, '')


def _column_metric(label: str, value: str, col_width: int, label_width: int, number_width: int, unit_width: int):
    number, unit = _split_num_unit(value)
    display_number = _fit(number, number_width)
    display_unit = _fit(unit, unit_width) if unit_width > 0 else ''
    return {
        'label': label,
        'number': display_number,
        'unit': display_unit,
        'col_width': col_width,
        'label_width': label_width,
        'number_width': number_width,
        'unit_width': unit_width,
    }


def _met_to_hours(met: str):
    text = (met or '').strip().upper()
    if not text:
        return None

    sign = 1
    if text.startswith(('T-', 'L-', '-')):
        sign = -1
        text = text[2:] if text[:2] in ('T-', 'L-') else text[1:]
    elif text.startswith('+'):
        text = text[1:]

    match = re.match(r'^(\d+):(\d{2}):(\d{2}):(\d{2})$', text)
    if not match:
        return None

    days, hours, minutes, seconds = map(int, match.groups())
    total = (days * 24) + hours + (minutes / 60.0) + (seconds / 3600.0)
    return sign * total


def _format_met(hours_value: float):
    sign = '-' if hours_value < 0 else ''
    total_seconds = int(abs(hours_value) * 3600)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f'{sign}{days:03d}:{hours:02d}:{minutes:02d}:{seconds:02d}'


def _site_num(value: float):
    if value >= 1_000_000:
        return f'{value / 1000.0:.0f}k'
    if value >= 10_000:
        return f'{value / 1000.0:.1f}k'
    if value >= 1_000:
        return f'{value / 1000.0:.2f}k'
    return f'{value:.0f}'


def _clamp(value: float, lower: float, upper: float):
    return max(lower, min(upper, value))


def _lerp(start: float, end: float, amount: float):
    return start + ((end - start) * _clamp(amount, 0.0, 1.0))


def _smoothstep(value: float):
    t = _clamp(value, 0.0, 1.0)
    return (3.0 * t * t) - (2.0 * t * t * t)


def _orbital_velocity(radius_km: float, semi_major_axis_km: float):
    value = 398600.4418 * ((2.0 / radius_km) - (1.0 / semi_major_axis_km))
    return math.sqrt(value) if value > 0 else 0.0


def _interp_profile(profile, seconds_value: float):
    if seconds_value <= profile[0][0]:
        return profile[0][1:]
    if seconds_value >= profile[-1][0]:
        return profile[-1][1:]

    for idx in range(len(profile) - 1):
        start = profile[idx]
        end = profile[idx + 1]
        if start[0] <= seconds_value < end[0]:
            amount = (seconds_value - start[0]) / (end[0] - start[0])
            return [start[i] + ((end[i] - start[i]) * amount) for i in range(1, len(start))]

    return profile[-1][1:]


def _noise(met_hours: float, seed: int, amplitude: float):
    raw = 43758.5453 * math.sin((17.13 * met_hours) + (31.97 * seed))
    return ((raw - math.floor(raw) - 0.5) * 2.0) * amplitude


def _solve_kepler(mean_anomaly: float, eccentricity: float):
    value = mean_anomaly + (eccentricity * math.sin(mean_anomaly))
    for _ in range(30):
        delta = (value - (eccentricity * math.sin(value)) - mean_anomaly) / (1 - (eccentricity * math.cos(value)))
        value -= delta
        if abs(delta) < 1e-12:
            break
    return value


def _phase_info(met_hours: float):
    if met_hours < 0:
        return ('prelaunch', 'PRE-LAUNCH')
    if met_hours < 0.1375:
        return ('ascent', 'ASCENT')
    if met_hours <= 2.03:
        return ('orbit', 'ORBIT INSERTION')
    if met_hours <= 25.145:
        return ('heo', 'HIGH EARTH ORBIT')
    if met_hours <= 102.633:
        return ('trans_lunar', 'TRANS-LUNAR COAST')
    if met_hours <= 138.883:
        return ('flyby', 'LUNAR FLYBY')
    if met_hours <= 217.483:
        return ('trans_earth', 'TRANS-EARTH COAST')
    if met_hours <= 217.713:
        return ('edl', 'ENTRY / DESCENT')
    return ('recovery', 'RECOVERY')


def _flight_day(met_hours: float):
    if met_hours < 17:
        return 'FD01'
    if met_hours < 41:
        return 'FD02'
    if met_hours < 61:
        return 'FD03'
    if met_hours < 79:
        return 'FD04'
    if met_hours < 103:
        return 'FD05'
    if met_hours < 127:
        return 'FD06'
    if met_hours < 151:
        return 'FD07'
    if met_hours < 175:
        return 'FD08'
    if met_hours < 199:
        return 'FD09'
    return 'FD10'


def _compute_live_telemetry(met_hours: float):
    phase_key, phase_label = _phase_info(met_hours)

    if phase_key == 'prelaunch':
        velocity = 0.0
        altitude = 0.0
        earth_dist = 6371.0
        moon_dist = 384400.0
        g_force = 1.0
    elif phase_key == 'ascent':
        seconds_value = 3600.0 * met_hours
        altitude, velocity_ms, g_force = _interp_profile(ASCENT_PROFILE, seconds_value)
        velocity = (velocity_ms / 1000.0) + _noise(met_hours, 1, 0.01)
        altitude = altitude + _noise(met_hours, 2, 0.2)
        earth_dist = 6371.0 + altitude
        moon_dist = 384400.0
        g_force = max(0.0, g_force + _noise(met_hours, 6, 0.02))
    elif phase_key == 'orbit':
        g_force = 0.0
        if met_hours < 0.833:
            altitude = 160.0 + (1646.0 * (1.0 - math.cos(((met_hours - 0.1375) / 0.6955) * math.pi)) / 2.0)
            velocity = _orbital_velocity(6371.0 + altitude, 7289.0)
        elif met_hours < 0.843:
            altitude = 1806.0
            velocity = _orbital_velocity(6371.0 + altitude, 7366.5)
            g_force = 0.12
        elif met_hours < 1.783:
            altitude = 1806.0 - (1621.0 * (1.0 - math.cos(((met_hours - 0.833) / 0.95) * math.pi)) / 2.0)
            velocity = _orbital_velocity(6371.0 + altitude, 7366.5)
        elif met_hours < 1.793:
            altitude = 205.0
            velocity = _lerp(8.2, 10.58, (met_hours - 1.783) / 0.01)
            g_force = 0.12
        else:
            altitude = 185.0 + (((met_hours - 2.03) / 0.5) * 500.0)
            velocity = _orbital_velocity(6371.0 + altitude, 41463.5)
        earth_dist = 6371.0 + altitude
        moon_dist = 384400.0 - altitude + _noise(met_hours, 7, 50)
        velocity = velocity + _noise(met_hours, 1, 0.008)
        altitude = altitude + _noise(met_hours, 2, 0.3)
        g_force = g_force + _noise(met_hours, 6, 0.001)
    elif phase_key == 'heo':
        eccentricity = 0.8418850314131706
        anomaly = ((2.0 * math.pi / HEO_PERIOD) * ((met_hours - 2.03) * 3600.0)) % (2.0 * math.pi)
        eccentric_anomaly = _solve_kepler(anomaly, eccentricity)
        earth_dist = 41463.5 * (1.0 - (eccentricity * math.cos(eccentric_anomaly)))
        altitude = earth_dist - 6371.0
        velocity = _orbital_velocity(earth_dist, 41463.5) + _noise(met_hours, 1, 0.005)
        moon_dist = 384400.0 - altitude + _noise(met_hours, 7, 50)
        altitude = altitude + _noise(met_hours, 2, 0.5)
        g_force = _noise(met_hours, 6, 0.001)
    elif phase_key == 'trans_lunar':
        progress = (met_hours - 25.145) / 77.488
        earth_dist = 6556.0 + (311661.0 * math.pow(progress, 0.78))
        altitude = earth_dist - 6371.0
        velocity = _orbital_velocity(earth_dist, 223600.0) + _noise(met_hours, 1, 0.005)
        moon_dist = max(66183.0, 384400.0 - earth_dist + 6371.0) + _noise(met_hours, 7, 20)
        g_force = _noise(met_hours, 6, 0.0005)
    elif phase_key == 'flyby':
        progress = (met_hours - 102.633) / 36.250000000000014
        if progress < 0.4928827586206896:
            lunar_dist = 66183.0 - (57933.0 * _smoothstep(progress / 0.4928827586206896))
            angle = math.pi * _smoothstep(progress / 0.4928827586206896)
        else:
            lunar_dist = 8250.0 + (57933.0 * _smoothstep((progress - 0.4928827586206896) / 0.5071172413793104))
            angle = math.pi + (0.75 * _smoothstep((progress - 0.4928827586206896) / 0.5071172413793104))
        earth_dist = math.sqrt((384400.0 ** 2) + (lunar_dist ** 2) - (768800.0 * lunar_dist * math.cos(angle)))
        base_vel = math.sqrt(0.6889 + (9805.6 / lunar_dist))
        velocity = math.sqrt((base_vel * base_vel) + 1.036324) + _noise(met_hours, 1, 0.008)
        altitude = lunar_dist - 1737.0
        moon_dist = lunar_dist + _noise(met_hours, 7, 0.5)
        g_force = _noise(met_hours, 6, 0.001)
    elif phase_key == 'trans_earth':
        progress = (met_hours - 138.883) / 78.6
        earth_dist = 6492.9 + (343507.1 * math.pow(1.0 - progress, 0.78))
        altitude = earth_dist - 6371.0
        velocity = _orbital_velocity(earth_dist, 235130.0) + _noise(met_hours, 1, 0.005)
        moon_dist = math.sqrt(((384400.0 - (0.85 * earth_dist)) ** 2) + (((0.3 * earth_dist) ** 2))) + _noise(met_hours, 7, 30)
        g_force = _noise(met_hours, 6, 0.0005)
    elif phase_key == 'edl':
        seconds_value = (met_hours - 217.483) * 3600.0
        altitude, velocity, g_force = _interp_profile(EDL_PROFILE, seconds_value)
        velocity = max(0.0, velocity + _noise(met_hours, 1, 0.02))
        altitude = max(0.0, altitude + _noise(met_hours, 2, 0.1))
        earth_dist = 6371.0 + altitude
        moon_dist = 384400.0
        g_force = max(0.0, g_force + _noise(met_hours, 6, 0.05))
    else:
        velocity = 0.0
        altitude = 0.0
        earth_dist = 6371.0
        moon_dist = 384400.0
        g_force = 1.0

    return {
        'phase': phase_label,
        'flight_day': _flight_day(met_hours),
        'velocity': f'{velocity:.2f} km/s',
        'g_force': f'{g_force:.3f} g',
        'altitude': f'{_site_num(max(0.0, altitude))} km',
        'earth_dist': f'{_site_num(max(0.0, earth_dist))} km',
        'moon_dist': f'{_site_num(max(0.0, moon_dist))} km',
    }


def _compute_live_data():
    now_utc = datetime.now(timezone.utc)
    met_hours = (now_utc - LAUNCH_DATE).total_seconds() / 3600.0
    live = _compute_live_telemetry(met_hours)
    live['mission_elapsed_time'] = _format_met(met_hours)
    live['mission_elapsed_hours'] = met_hours
    return live


def _draw_box(conn: Connection, x: int, y: int, width: int, title: str, rows,
              border='CYAN', titlec='YELLOW', labelc='LTBLUE', valuec='WHITE',
              right_align_values=False):
    inner = max(1, width - 2)
    conn.SendTML(f'<AT x={x} y={y}><{border}><UL-CORNER><HLINE n={inner}><UR-CORNER>')
    conn.SendTML(f'<AT x={x} y={y+1}><VLINE><{titlec}>{_fit(title, inner):<{inner}}<{border}><VLINE>')
    conn.SendTML(f'<AT x={x} y={y+2}><VLINE><HLINE n={inner}><VLINE>')

    row_y = y + 3
    value_width = max(1, inner - 7)

    for label, value in rows:
        shown = _fit(value, value_width)
        shown = f'{shown:>{value_width}}' if right_align_values else f'{shown:<{value_width}}'

        conn.SendTML(
            f'<AT x={x} y={row_y}><VLINE>'
            f'<{labelc}>{label:<6} '
            f'<{valuec}>{shown}'
            f'<{border}><VLINE>'
        )
        row_y += 1

    conn.SendTML(f'<AT x={x} y={row_y}><LL-CORNER><HLINE n={inner}><LR-CORNER>')


def _cubic_point(p0, p1, p2, p3, t):
    omt = 1.0 - t
    omt2 = omt * omt
    t2 = t * t
    return {
        'x': (omt2 * omt * p0['x']) + (3 * omt2 * t * p1['x']) + (3 * omt * t2 * p2['x']) + (t2 * t * p3['x']),
        'y': (omt2 * omt * p0['y']) + (3 * omt2 * t * p1['y']) + (3 * omt * t2 * p2['y']) + (t2 * t * p3['y']),
    }


def _circular_orbit_point(met_hours: float):
    angle = (-math.pi / 2.0) + met_hours * math.pi
    return {
        'x': EARTH_CENTER['x'] + (50.0 * math.cos(angle)),
        'y': EARTH_CENTER['y'] + (50.0 * math.sin(angle)),
    }


def _spiral_angle(progress: float):
    return (-math.pi / 2.0) + (progress * math.pi * 3.75)


def _build_to_moon_curve():
    angle = _spiral_angle(1.0)
    radius = 85.0
    turns = 2.0 * math.pi * 1.875
    dx = (35.0 * math.cos(angle)) - (radius * math.sin(angle) * turns)
    dy = (35.0 * math.sin(angle)) + (radius * math.cos(angle) * turns)
    magnitude = math.sqrt((dx * dx) + (dy * dy))

    start = {
        'x': EARTH_CENTER['x'] + (radius * math.cos(angle)),
        'y': EARTH_CENTER['y'] + (radius * math.sin(angle)),
    }
    direction = {'dx': dx / magnitude, 'dy': dy / magnitude}
    moon_touch = {
        'x': MOON_CENTER['x'] + (45.0 * math.cos(MOON_ENTRY_ANGLE)),
        'y': MOON_CENTER['y'] + (45.0 * math.sin(MOON_ENTRY_ANGLE)),
    }
    tangent = {'dx': -math.sin(MOON_ENTRY_ANGLE), 'dy': math.cos(MOON_ENTRY_ANGLE)}

    return {
        'p0': start,
        'p1': {'x': start['x'] + (200.0 * direction['dx']), 'y': start['y'] + (200.0 * direction['dy'])},
        'p2': {'x': moon_touch['x'] - (200.0 * tangent['dx']), 'y': moon_touch['y'] - (200.0 * tangent['dy'])},
        'p3': moon_touch,
    }


def _build_from_moon_curve():
    moon_touch = {
        'x': MOON_CENTER['x'] + (45.0 * math.cos(MOON_EXIT_ANGLE)),
        'y': MOON_CENTER['y'] + (45.0 * math.sin(MOON_EXIT_ANGLE)),
    }
    tangent = {'dx': -math.sin(MOON_EXIT_ANGLE), 'dy': math.cos(MOON_EXIT_ANGLE)}
    earth_touch = {'x': EARTH_CENTER['x'] + 55.0, 'y': EARTH_CENTER['y'] + 25.0}

    return {
        'p0': moon_touch,
        'p1': {'x': moon_touch['x'] + (200.0 * tangent['dx']), 'y': moon_touch['y'] + (200.0 * tangent['dy'])},
        'p2': {'x': 350.0, 'y': 260.0},
        'p3': earth_touch,
    }


TO_MOON_CURVE = _build_to_moon_curve()
FROM_MOON_CURVE = _build_from_moon_curve()


def _trajectory_point(met_hours: float):
    if met_hours <= 0.0:
        return _circular_orbit_point(0.0)
    if met_hours <= 2.0:
        return _circular_orbit_point(met_hours)
    if met_hours <= 25.5:
        progress = (met_hours - 2.0) / 23.5
        radius = 50.0 + (35.0 * progress)
        angle = _spiral_angle(progress)
        return {
            'x': EARTH_CENTER['x'] + (radius * math.cos(angle)),
            'y': EARTH_CENTER['y'] + (radius * math.sin(angle)),
        }
    if met_hours <= 115.0:
        return _cubic_point(TO_MOON_CURVE['p0'], TO_MOON_CURVE['p1'], TO_MOON_CURVE['p2'], TO_MOON_CURVE['p3'], (met_hours - 25.5) / 89.5)
    if met_hours <= 140.0:
        angle = MOON_ENTRY_ANGLE + (((met_hours - 115.0) / 25.0) * (MOON_EXIT_ANGLE - MOON_ENTRY_ANGLE))
        return {
            'x': MOON_CENTER['x'] + (45.0 * math.cos(angle)),
            'y': MOON_CENTER['y'] + (45.0 * math.sin(angle)),
        }
    if met_hours <= 209.0:
        return _cubic_point(FROM_MOON_CURVE['p0'], FROM_MOON_CURVE['p1'], FROM_MOON_CURVE['p2'], FROM_MOON_CURVE['p3'], (met_hours - 140.0) / 69.0)
    if met_hours <= 217.8:
        progress = (met_hours - 209.0) / 8.8
        return {
            'x': FROM_MOON_CURVE['p3']['x'] + ((EARTH_CENTER['x'] - FROM_MOON_CURVE['p3']['x']) * progress),
            'y': FROM_MOON_CURVE['p3']['y'] + ((EARTH_CENTER['y'] - FROM_MOON_CURVE['p3']['y']) * progress),
        }
    return {'x': EARTH_CENTER['x'], 'y': EARTH_CENTER['y']}


def _sample_segment(start_met: float, end_met: float, steps: int):
    points = []
    for idx in range(steps + 1):
        met = start_met + (((end_met - start_met) * idx) / steps)
        points.append(_trajectory_point(met))
    return points


def _render_orbit_map(gfxmode, map_lines: int, met_hours: float):
    out_width, out_height = GFX_MODES[gfxmode]['out_size']
    map_height = min(out_height, map_lines * 8)

    image = Image.new('RGB', (out_width, out_height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale = min(out_width / 1000.0, map_height / 280.0)
    inner_width = 1000.0 * scale
    inner_height = 280.0 * scale
    offset_x = (out_width - inner_width) / 2.0
    offset_y = (map_height - inner_height) / 2.0

    def tp(point):
        return (offset_x + (point['x'] * scale), offset_y + (point['y'] * scale))

    def circle(point, radius, fill=None, outline=None, width=1):
        px, py = tp(point)
        pr = radius * scale
        draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=fill, outline=outline, width=width)

    dim_width = max(1, int(round(scale * 4.0)))
    bright_width = max(1, int(round(scale * 5.0)))
    marker_radius = max(2, int(round(scale * 7.0)))
    earth_outline = max(1, int(round(scale * 3.0)))

    for name, start_met, end_met, steps in TRAJECTORY_SEGMENTS:
        transformed = [tp(point) for point in _sample_segment(start_met, end_met, steps)]
        draw.line(transformed, fill=FUTURE_ORBIT_COLOR, width=dim_width)

    if met_hours >= 0:
        clamped_met = max(0.0, min(met_hours, 217.8))
        for name, start_met, end_met, steps in TRAJECTORY_SEGMENTS:
            if clamped_met < start_met:
                continue
            visible_end = min(clamped_met, end_met)
            visible_steps = max(1, int(round(steps * ((visible_end - start_met) / (end_met - start_met)))))
            visible_points = _sample_segment(start_met, visible_end, visible_steps)
            if visible_end < end_met:
                visible_points.append(_trajectory_point(clamped_met))
            draw.line([tp(point) for point in visible_points], fill=PAST_ORBIT_COLOR, width=bright_width)

    circle({'x': EARTH_CENTER['x'], 'y': EARTH_CENTER['y']}, 35.0, fill=(30, 86, 180), outline=(170, 210, 255), width=earth_outline)
    circle({'x': MOON_CENTER['x'], 'y': MOON_CENTER['y']}, 12.0, fill=(136, 136, 136), outline=(220, 220, 220), width=1)

    if met_hours >= 0:
        current = _trajectory_point(max(0.0, min(met_hours, 217.8)))
        px, py = tp(current)
        draw.ellipse((px - marker_radius, py - marker_radius, px + marker_radius, py + marker_radius), fill=(0, 255, 136), outline=(255, 255, 255), width=1)

    return image


def _supports_split_graphics(conn: Connection):
    if conn.T56KVer <= 0:
        return False
    if conn.encoder.txt_geo[1] < 22:
        return False
    if conn.QueryFeature(TT.SPLIT_SCR) >= 0x80:
        return False
    return conn.QueryFeature(TT.PRADDR) < 0x80


def _choose_gfxmode(conn: Connection):
    if 'PET64' in conn.mode:
        return gfxmodes.C64HI
    if conn.mode == 'PET264':
        return gfxmodes.P4HI
    return conn.encoder.def_gfxmode if conn.encoder.def_gfxmode is not None else conn.encoder.gfxmodes[0]


def _disable_split(conn: Connection):
    if conn.T56KVer > 0 and conn.QueryFeature(TT.SPLIT_SCR) < 0x80:
        conn.SendTML(f'<NUL n=2><SPLIT bgbottom={conn.encoder.colors.get("BLACK", 0)} mode="_C.mode"><CURSOR>')


def _draw_text_screen(conn: Connection, data):
    scwidth, scheight = conn.encoder.txt_geo
    _disable_split(conn)
    conn.SendTML(f'<TEXT page=0 border={conn.style.BoColor} background={conn.style.BgColor}><CLR>')
    RenderMenuTitle(conn, 'Artemis')

    phase = _fit(data['phase'], scwidth - 18)
    conn.SendTML(f'<AT x=0 y=3><GREY3><HLINE n={scwidth}>')
    conn.SendTML(f'<AT x=1 y=4><YELLOW>Mission Time:   <WHITE>{_fit(data["mission_elapsed_time"], scwidth - 17)}')
    conn.SendTML(f'<AT x=1 y=5><YELLOW>Phase:          <WHITE>{phase}')
    conn.SendTML(f'<AT x=1 y=6><YELLOW>Flight Day:     <WHITE>{_fit(data["flight_day"], scwidth - 17)}')
    conn.SendTML(f'<AT x=0 y=7><GREY3><HLINE n={scwidth}>')

    left_x = 1
    gap = 2
    box_w = max(18, (scwidth - 4) // 2)
    right_x = left_x + box_w + gap

    if right_x + box_w > scwidth:
        box_w = (scwidth - 3) // 2
        right_x = left_x + box_w + 1

    _draw_box(
        conn, left_x, 9, box_w, 'DYNAMICS',
        [
            ('Vel', _fmt_num_unit(data['velocity'], 'km/s', 2)),
            ('Acc', _fmt_num_unit(data['g_force'], 'g', 2)),
        ],
        right_align_values=False
    )

    _draw_box(
        conn, right_x, 9, box_w, 'DISTANCE',
        [
            ('Earth', _with_unit(data['earth_dist'], 'km')),
            ('Moon', _with_unit(data['moon_dist'], 'km')),
        ],
        right_align_values=True
    )

    footer_y = min(scheight - 2, 23)
    conn.SendTML(f'<AT x=0 y={footer_y}><GREY3><HLINE n={scwidth}>')
    conn.SendTML(f'<AT x=1 y={footer_y + 1}><RVSON><YELLOW>RETURN<RVSOFF><WHITE> refresh  <GREY2>AUTO 60s  <RVSON><YELLOW><BACK><RVSOFF><WHITE> menu')


def _draw_split_screen(conn: Connection, data):
    if not _supports_split_graphics(conn):
        return False

    gfxmode = _choose_gfxmode(conn)
    scwidth, scheight = conn.encoder.txt_geo
    map_lines = max(12, min(14, scheight - 10))
    met_hours = data.get('mission_elapsed_hours')
    if met_hours is None:
        met_hours = _met_to_hours(data['mission_elapsed_time'])
    orbit = _render_orbit_map(gfxmode, map_lines, 0.0 if met_hours is None else met_hours)

    if FT.SendBitmap(
        conn,
        orbit,
        lines=map_lines,
        display=False,
        gfxmode=gfxmode,
        preproc=PreProcess(brightness=1.0, contrast=1.4, saturation=1.2),
        dither=dithertype.NONE
    ) is False:
        return False

    conn.SendTML(
        f'<SPLIT row={map_lines} multi=False '
        f'bgtop={conn.encoder.colors.get("BLACK", 0)} '
        f'bgbottom={conn.style.BgColor} mode={conn.mode}><CURSOR><CLR>'
    )

    met = _fit(data['mission_elapsed_time'], 14)
    header = f'ARTEMIS II {met}'
    if data['flight_day']:
        header = f'{header} {data["flight_day"]}'

    phase = _fit(data['phase'], scwidth - 7)
    left_col_width = max(10, scwidth // 2)
    right_col_width = max(10, scwidth - left_col_width)
    right_col_x = left_col_width
    dyn_label_width = 5
    dist_label_width = 7
    dyn_values = [
        _fmt_num_unit(data['velocity'], 'km/s', 2),
        _fmt_num_unit(data['g_force'], 'g', 2),
    ]
    dist_values = [
        _with_unit(data['earth_dist'], 'km'),
        _with_unit(data['moon_dist'], 'km'),
    ]
    dyn_numbers = [_split_num_unit(value)[0] for value in dyn_values]
    dyn_units = [_split_num_unit(value)[1] for value in dyn_values]
    dist_numbers = [_split_num_unit(value)[0] for value in dist_values]
    dist_units = [_split_num_unit(value)[1] for value in dist_values]
    dyn_unit_width = max(len(unit) for unit in dyn_units)
    dist_unit_width = max(len(unit) for unit in dist_units)
    dyn_number_width = max(len(number) for number in dyn_numbers)
    dist_number_width = max(len(number) for number in dist_numbers)

    row0_left = _fit('DYNAMICS', left_col_width)
    row0_right = _fit('DISTANCE', right_col_width)
    row1_left = _column_metric('VEL', dyn_values[0], left_col_width, dyn_label_width, dyn_number_width, dyn_unit_width)
    row1_right = _column_metric('EARTH', dist_values[0], right_col_width, dist_label_width, dist_number_width, dist_unit_width)
    row2_left = _column_metric('ACC', dyn_values[1], left_col_width, dyn_label_width, dyn_number_width, dyn_unit_width)
    row2_right = _column_metric('MOON', dist_values[1], right_col_width, dist_label_width, dist_number_width, dist_unit_width)

    def draw_metric(col_x: int, y: int, metric):
        unit_offset = metric['label_width'] + metric['number_width']
        conn.SendTML(f'<AT x={col_x} y={y}><LTBLUE>{metric["label"]:<{metric["label_width"]}}')
        conn.SendTML(f'<AT x={col_x + metric["label_width"]} y={y}><WHITE>{metric["number"]:>{metric["number_width"]}}')
        if metric['unit_width'] > 0:
            conn.SendTML(f'<AT x={col_x + unit_offset} y={y}><WHITE> {metric["unit"]:<{metric["unit_width"]}}')

    conn.SendTML(f'<AT x=0 y=0><YELLOW>{_fit(header, scwidth)}')
    conn.SendTML(f'<AT x=0 y=1><LTBLUE>PHASE <WHITE>{phase}')
    conn.SendTML(f'<AT x=0 y=2><GREY3><HLINE n={scwidth}>')
    conn.SendTML(f'<AT x=0 y=3><YELLOW>{row0_left}')
    conn.SendTML(f'<AT x={right_col_x} y=3><YELLOW>{row0_right}')
    draw_metric(0, 4, row1_left)
    draw_metric(right_col_x, 4, row1_right)
    draw_metric(0, 5, row2_left)
    draw_metric(right_col_x, 5, row2_right)
    conn.SendTML(f'<AT x=0 y=6><GREY3><HLINE n={scwidth}>')
    conn.SendTML(f'<AT x=0 y=7><RVSON><YELLOW>RETURN<RVSOFF><WHITE> refresh  <GREY2>AUTO 60s  <RVSON><YELLOW><BACK><RVSOFF><WHITE> menu')
    return True


def _draw_error(conn: Connection, message: str):
    scwidth, scheight = conn.encoder.txt_geo
    _disable_split(conn)
    conn.SendTML(f'<TEXT page=0 border={conn.style.BoColor} background={conn.style.BgColor}><CLR>')
    RenderMenuTitle(conn, 'Artemis')
    conn.SendTML('<AT x=1 y=5><RED>Unable to load Artemis telemetry.')
    conn.SendTML(f'<AT x=1 y=7><GREY2>{_fit(message, scwidth - 2)}')
    footer_y = min(scheight - 2, 22)
    conn.SendTML(f'<AT x=0 y={footer_y}><GREY3><HLINE n={scwidth}>')
    conn.SendTML(f'<AT x=1 y={footer_y + 1}><RVSON><YELLOW>RETURN<RVSOFF><WHITE> retry  <GREY2>AUTO 60s  <RVSON><YELLOW><BACK><RVSOFF><WHITE> menu')


def _wait_for_action(conn: Connection, refresh: str, back: str, timeout: int = AUTO_REFRESH_SECONDS):
    deadline = time.monotonic() + timeout
    while conn.connected:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _LOG('ARTEMIS - auto refresh triggered', id=conn.id, v=4)
            return refresh

        try:
            ready, _, _ = select.select((conn.socket,), (), (), remaining)
        except Exception as exc:
            _LOG(bcolors.WARNING + f'ARTEMIS - input wait failed: {exc}' + bcolors.ENDC, id=conn.id, v=2)
            conn.connected = False
            return back

        if not ready:
            _LOG('ARTEMIS - auto refresh triggered', id=conn.id, v=4)
            return refresh

        try:
            key = conn.socket.recv(1)
            if key == b'':
                conn.connected = False
                return back

            conn.inbytes += 1
            value = key[0]
            if ('PET' in conn.mode) and (value in range(0xC1, 0xDA + 1)):
                value -= 96
            key = chr(value)
        except Exception as exc:
            _LOG(bcolors.WARNING + f'ARTEMIS - input read failed: {exc}' + bcolors.ENDC, id=conn.id, v=2)
            conn.connected = False
            return back

        if key == back or key == refresh:
            return key


def plugFunction(conn: Connection, url: str = DEFAULT_URL):
    back = conn.encoder.back
    refresh = conn.encoder.nl

    try:
        while conn.connected:
            try:
                data = _get_artemis_data(url)
                _LOG('ARTEMIS - mission data updated', id=conn.id, v=4)
                drawn = False

                if _supports_split_graphics(conn):
                    try:
                        drawn = _draw_split_screen(conn, data)
                    except Exception as gfx_exc:
                        _LOG(bcolors.WARNING + f'ARTEMIS - split render failed: {gfx_exc}' + bcolors.ENDC, id=conn.id, v=2)

                if not drawn:
                    _draw_text_screen(conn, data)
            except Exception as exc:
                _LOG(bcolors.WARNING + f'ARTEMIS - {exc}' + bcolors.ENDC, id=conn.id, v=2)
                _draw_error(conn, str(exc))

            key = _wait_for_action(conn, refresh, back)
            if (not conn.connected) or key == back:
                break
    finally:
        _disable_split(conn)
