<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Vendored libraries

Third-party files the stats page (`/storyteller/stats`) loads, copied unmodified from their npm packages so the page
needs no build step and no CDN. Each keeps its own licence (all compatible with the app's AGPL-3.0-or-later).

| File | Package | Licence | sha256 |
|---|---|---|---|
| `echarts.min.js` | [echarts](https://echarts.apache.org) 6.1.0, `dist/echarts.min.js` | Apache-2.0 (`LICENSE-echarts`, `NOTICE-echarts`) | `b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0` |
| `topojson-client.min.js` | [topojson-client](https://github.com/topojson/topojson-client) 3.1.0, `dist/topojson-client.min.js` | ISC (`LICENSE-topojson-client`) | `25cd02ae486cc5063e0215a4e4cfb15de83700c87ac48bac4d57dc6aaf3ebb89` |
| `../../data/countries-110m.json` | [world-atlas](https://github.com/topojson/world-atlas) 2.0.2, `countries-110m.json` (Natural Earth, public domain) | ISC (`LICENSE-world-atlas`) | `2516c915867c7baf18ddec727aec46c315541a07cfb3d79a6559b05d5e94eee8` |

To update one, `npm pack <package>@<version>`, copy the same file over, and update its row (version and sha256).
