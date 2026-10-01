"""
topo package - the smart-home IoT network.
Lets scripts in other folders do:  from topo.smart_home_topo import build_network
"""

import os
import sys

# The files in topo/ import each other by plain name (e.g. `from mqtt_traffic import ...`).
# Adding this folder to Python's search path keeps those imports working when topo/
# is imported as a package from another folder.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))