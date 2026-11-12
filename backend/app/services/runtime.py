"""Small in-memory runtime settings shared by the simulation runner and the API (never business data).

pause_on_alert: while the simulation runs by itself, stop it automatically when a new HIGH/CRITICAL
coordinator alert is raised, so the presenter can react before the situation moves on.
"""
RUNNER = {"pause_on_alert": True, "last_error": None}
SPEEDS = (1.0, 5.0, 15.0, 30.0)      # simulated minutes per real second
TICK_SECONDS = 2.0
