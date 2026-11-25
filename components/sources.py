import threading
import time


class PollingSource:
    """Data from somewhere slow (like a web API), fetched in the background every `interval`
    seconds so drawing never waits on it. Components read it with RenderContext.data()."""

    interval = 60
    # After a failed fetch, try again after this many seconds (or interval, if shorter)
    retry_interval = 60

    def __init__(self):
        self.data = None        # the last data fetched; kept when a later fetch fails
        self.error = None
        self.updated_at = None
        self._thread = None
        self._lock = threading.Lock()

    def current(self):
        """The latest data, or None until a fetch has worked. The first call starts fetching,
        so a source nothing on the display uses never fetches."""
        if self._thread is None:
            with self._lock:
                if self._thread is None:
                    self._thread = threading.Thread(target=self._loop, daemon=True, name=type(self).__name__)
                    self._thread.start()
        return self.data

    def _loop(self):
        while True:
            try:
                self.data = self.fetch()
                self.error = None
                self.updated_at = time.time()
                delay = self.interval
            except Exception as e:
                # e.g. no network yet at boot: keep showing the last good data and retry sooner
                self.error = f"{type(e).__name__}: {e}"
                print(f"{type(self).__name__}: fetch failed: {self.error}", flush=True)
                delay = min(self.interval, self.retry_interval)
            time.sleep(delay)

    def fetch(self):
        raise NotImplementedError
