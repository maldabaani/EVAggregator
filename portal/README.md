# EV Aggregator — Operator Portal

Angular 17 standalone-components app for CPO/eMSP operators: partner
onboarding, tariff management, fleet dashboards. See
`../docs/00_Engineering_Standards.md` for shared conventions.

## Quickstart

```bash
npm install
npm start          # dev server on http://localhost:4200
npm run build      # production build -> dist/portal
npm test           # unit tests (Karma + Jasmine)
```

## Running tests without a system Chrome install

`ng test` needs a Chrome/Chromium binary. If none is on your machine, point
`CHROME_BIN` at one before running tests:

```bash
CHROME_BIN=/path/to/chrome npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox --code-coverage
```

The `ChromeHeadlessNoSandbox` launcher (defined in `karma.conf.js`) adds
`--no-sandbox`, needed when running as root (e.g. in a container). CI images
with a pre-installed system Chrome don't need `CHROME_BIN` set at all.
