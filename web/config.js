// Deployment configuration for the explorer. Edit per host.
//
//   apiBase: base URL of the always-on container's API.
//     ""  → same origin (use this when the container itself serves this page,
//           i.e. the local Windows deployment).
//     "https://badminton.example.com" → when this page is on GitHub Pages and
//           the home container is exposed over HTTPS (e.g. a Cloudflare/Tailscale
//           tunnel). Must be HTTPS — a browser on an https:// page cannot call a
//           plain http:// localhost server (mixed content is blocked).
//
// On GitHub Pages with no reachable container, leave apiBase "" — the site then
// runs purely on the published data.json snapshot and shows an "offline" note.
window.BADMINTON_CONFIG = {
  apiBase: "",
};
