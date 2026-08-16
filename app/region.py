"""Location-aware framing, derived from Cloudflare's country header.

Replaces the old CS_HOME_REGION: instead of one deployment-wide tagline and map
default, both are derived per-request from the visitor's own country. Cloudflare
sits in front of this app (see static_url()'s comment in app/templating.py) and adds
CF-IPCountry to every proxied request on every plan, including free, so this needs no
new infrastructure. Country-level only for now — city-level would need Cloudflare's
IP Geolocation add-on or a fallback lookup, and isn't worth it yet.

Display-only and request-scoped: this is read from a header and handed to a template
on the same request, never written to a session, a log line, or a database row. That
matches the "no IP address persisted anywhere" promise in SECURITY.md that coordinate
fuzzing already keeps.

A country with no entry here — including Cloudflare's own "unknown" (XX) and Tor (T1)
codes, and local dev where there is no Cloudflare in front at all — falls back to the
plain global tagline and to Settings.default_lat/lng, which is the Humboldt origin
point. That fallback doubles as the origin nod rather than needing special-casing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    name: str
    lat: float
    lng: float
    zoom: int = 5  # Country-level view; "use my location" narrows it from here.


# Approximate capital-city coordinates, not true geographic centroids — this only
# sets the map's starting view, so "somewhere in the country" is close enough.
# Coverage favours countries likely to send real traffic; a missing one just falls
# back to the global framing above rather than failing.
REGIONS: dict[str, Region] = {
    "US": Region("the United States", 38.9072, -77.0369),
    "CA": Region("Canada", 45.4215, -75.6972),
    "MX": Region("Mexico", 19.4326, -99.1332),
    "GT": Region("Guatemala", 14.6349, -90.5069),
    "BZ": Region("Belize", 17.2510, -88.7590),
    "HN": Region("Honduras", 14.0723, -87.1921),
    "SV": Region("El Salvador", 13.6929, -89.2182),
    "NI": Region("Nicaragua", 12.1150, -86.2362),
    "CR": Region("Costa Rica", 9.9281, -84.0907),
    "PA": Region("Panama", 8.9824, -79.5199),
    "CU": Region("Cuba", 23.1136, -82.3666),
    "JM": Region("Jamaica", 17.9712, -76.7936),
    "HT": Region("Haiti", 18.5944, -72.3074),
    "DO": Region("the Dominican Republic", 18.4861, -69.9312),
    "PR": Region("Puerto Rico", 18.4655, -66.1057),
    "TT": Region("Trinidad and Tobago", 10.6549, -61.5019),
    "BS": Region("the Bahamas", 25.0343, -77.3963),
    "BR": Region("Brazil", -15.7939, -47.8828),
    "AR": Region("Argentina", -34.6037, -58.3816),
    "CL": Region("Chile", -33.4489, -70.6693),
    "CO": Region("Colombia", 4.7110, -74.0721),
    "PE": Region("Peru", -12.0464, -77.0428),
    "VE": Region("Venezuela", 10.4806, -66.9036),
    "EC": Region("Ecuador", -0.1807, -78.4678),
    "BO": Region("Bolivia", -16.4897, -68.1193),
    "PY": Region("Paraguay", -25.2637, -57.5759),
    "UY": Region("Uruguay", -34.9011, -56.1645),
    "GY": Region("Guyana", 6.8013, -58.1551),
    "SR": Region("Suriname", 5.8520, -55.2038),
    "GB": Region("the United Kingdom", 51.5074, -0.1278),
    "IE": Region("Ireland", 53.3498, -6.2603),
    "FR": Region("France", 48.8566, 2.3522),
    "DE": Region("Germany", 52.5200, 13.4050),
    "ES": Region("Spain", 40.4168, -3.7038),
    "PT": Region("Portugal", 38.7223, -9.1393),
    "IT": Region("Italy", 41.9028, 12.4964),
    "NL": Region("the Netherlands", 52.3676, 4.9041),
    "BE": Region("Belgium", 50.8503, 4.3517),
    "CH": Region("Switzerland", 46.9480, 7.4474),
    "AT": Region("Austria", 48.2082, 16.3738),
    "SE": Region("Sweden", 59.3293, 18.0686),
    "NO": Region("Norway", 59.9139, 10.7522),
    "DK": Region("Denmark", 55.6761, 12.5683),
    "FI": Region("Finland", 60.1699, 24.9384),
    "IS": Region("Iceland", 64.1466, -21.9426),
    "PL": Region("Poland", 52.2297, 21.0122),
    "CZ": Region("Czechia", 50.0755, 14.4378),
    "SK": Region("Slovakia", 48.1486, 17.1077),
    "HU": Region("Hungary", 47.4979, 19.0402),
    "RO": Region("Romania", 44.4268, 26.1025),
    "BG": Region("Bulgaria", 42.6977, 23.3219),
    "GR": Region("Greece", 37.9838, 23.7275),
    "HR": Region("Croatia", 45.8150, 15.9819),
    "RS": Region("Serbia", 44.7866, 20.4489),
    "UA": Region("Ukraine", 50.4501, 30.5234),
    "EE": Region("Estonia", 59.4370, 24.7536),
    "LV": Region("Latvia", 56.9496, 24.1052),
    "LT": Region("Lithuania", 54.6872, 25.2797),
    "LU": Region("Luxembourg", 49.6116, 6.1319),
    "MT": Region("Malta", 35.8989, 14.5146),
    "CY": Region("Cyprus", 35.1856, 33.3823),
    "SI": Region("Slovenia", 46.0569, 14.5058),
    "IL": Region("Israel", 31.7683, 35.2137),
    "TR": Region("Turkey", 39.9334, 32.8597),
    "SA": Region("Saudi Arabia", 24.7136, 46.6753),
    "AE": Region("the United Arab Emirates", 24.4539, 54.3773),
    "QA": Region("Qatar", 25.2854, 51.5310),
    "JO": Region("Jordan", 31.9454, 35.9284),
    "LB": Region("Lebanon", 33.8938, 35.5018),
    "KW": Region("Kuwait", 29.3759, 47.9774),
    "OM": Region("Oman", 23.5859, 58.4059),
    "KE": Region("Kenya", -1.2921, 36.8219),
    "NG": Region("Nigeria", 9.0765, 7.3986),
    "ZA": Region("South Africa", -25.7479, 28.2293),
    "GH": Region("Ghana", 5.6037, -0.1870),
    "ET": Region("Ethiopia", 9.0250, 38.7469),
    "TZ": Region("Tanzania", -6.1630, 35.7516),
    "UG": Region("Uganda", 0.3476, 32.5825),
    "RW": Region("Rwanda", -1.9403, 30.0586),
    "EG": Region("Egypt", 30.0444, 31.2357),
    "MA": Region("Morocco", 34.0209, -6.8416),
    "DZ": Region("Algeria", 36.7538, 3.0588),
    "TN": Region("Tunisia", 36.8065, 10.1815),
    "SN": Region("Senegal", 14.7167, -17.4677),
    "CM": Region("Cameroon", 3.8480, 11.5021),
    "ZM": Region("Zambia", -15.3875, 28.3228),
    "ZW": Region("Zimbabwe", -17.8252, 31.0335),
    "NA": Region("Namibia", -22.5609, 17.0658),
    "BW": Region("Botswana", -24.6282, 25.9231),
    "MZ": Region("Mozambique", -25.9692, 32.5732),
    "MW": Region("Malawi", -13.9626, 33.7741),
    "IN": Region("India", 28.6139, 77.2090),
    "PK": Region("Pakistan", 33.6844, 73.0479),
    "BD": Region("Bangladesh", 23.8103, 90.4125),
    "LK": Region("Sri Lanka", 6.9271, 79.8612),
    "NP": Region("Nepal", 27.7172, 85.3240),
    "CN": Region("China", 39.9042, 116.4074),
    "JP": Region("Japan", 35.6762, 139.6503),
    "KR": Region("South Korea", 37.5665, 126.9780),
    "TW": Region("Taiwan", 25.0330, 121.5654),
    "HK": Region("Hong Kong", 22.3193, 114.1694),
    "MN": Region("Mongolia", 47.8864, 106.9057),
    "PH": Region("the Philippines", 14.5995, 120.9842),
    "ID": Region("Indonesia", -6.2088, 106.8456),
    "VN": Region("Vietnam", 21.0278, 105.8342),
    "TH": Region("Thailand", 13.7563, 100.5018),
    "MY": Region("Malaysia", 3.1390, 101.6869),
    "SG": Region("Singapore", 1.3521, 103.8198),
    "MM": Region("Myanmar", 19.7633, 96.0785),
    "KH": Region("Cambodia", 11.5564, 104.9282),
    "LA": Region("Laos", 17.9757, 102.6331),
    "AU": Region("Australia", -35.2809, 149.1300),
    "NZ": Region("New Zealand", -41.2865, 174.7762),
    "FJ": Region("Fiji", -18.1416, 178.4419),
    "PG": Region("Papua New Guinea", -9.4438, 147.1803),
}


def region_for(country_code: str | None) -> Region | None:
    if not country_code:
        return None
    return REGIONS.get(country_code.strip().upper())
