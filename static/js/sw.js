// Tombstone. The PWA layer was removed; this file only exists to retire the service
// worker that earlier visitors installed.
//
// Deleting the route instead would leave that worker registered in their browser
// indefinitely, still serving assets from its old cache — so it has to be replaced
// by one that deletes its caches and unregisters itself. Keep this served until the
// old worker can be assumed gone everywhere, then remove the file and its route.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: 'window' });
      // Reload so the page stops being served by this worker immediately.
      clients.forEach((client) => client.navigate(client.url));
    })()
  );
});
