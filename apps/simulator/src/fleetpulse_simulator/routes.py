"""Looping routes around Gothenburg. The first waypoint of each route is the home port.

Coordinates are approximate and chosen to stay on the water at map zoom levels
used by the dashboard.
"""

from fleetpulse_simulator.geo import Position

ROUTES: list[list[Position]] = [
    # River shuttle: Stenpiren - Lindholmen - Eriksberg - Klippan
    [(57.7058, 11.9590), (57.7080, 11.9420), (57.7015, 11.9150), (57.6935, 11.9030)],
    # Southern archipelago ferry: Saltholmen - Asperö - Brännö - Styrsö - Vrångö
    [
        (57.6595, 11.8390),
        (57.6565, 11.8130),
        (57.6415, 11.7780),
        (57.6170, 11.7840),
        (57.5800, 11.7740),
    ],
    # Harbour mouth to Vinga lighthouse
    [(57.6880, 11.8700), (57.6700, 11.7900), (57.6450, 11.6800), (57.6330, 11.6150)],
    # Northern archipelago: Arendal - Hönö - Öckerö
    [(57.6930, 11.8380), (57.6880, 11.7500), (57.6940, 11.6620), (57.7120, 11.6560)],
    # Donsö - Vargö loop
    [(57.6070, 11.8020), (57.5980, 11.8350), (57.6150, 11.8550), (57.6300, 11.8250)],
]
