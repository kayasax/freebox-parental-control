# Freebox Parental Control for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Control **per-profile Internet access** on your **Freebox** directly from Home
Assistant — the parental / network-control feature the official Freebox
integration does not provide.

Each Freebox *network-control profile* (typically one per family member) is
exposed as:

- a **switch** — `ON` = that profile has Internet; turn it **OFF** to cut the
  Internet, **ON** to restore it;
- a **sensor** — the number of devices assigned to the profile, with their
  resolved names as attributes.

Everything runs **locally** against `http://mafreebox.freebox.fr`. Nothing goes
through the Freebox cloud, and the app token is stored in the config entry — no
token in any file.

## Why this exists

The official core Freebox integration only exposes the global Wi-Fi switch and
device-tracker presence. **No** existing integration controls the parental /
network-control **profiles**. This integration fills that gap with a real,
config-flow-driven custom component.

## Installation

Setup has **three** stages: install the code (HACS), add the integration in
Home Assistant, then grant rights on the Freebox. Do them in order.

### Stage 1 — Install via HACS (custom repository)

1. In the Home Assistant **left sidebar**, open **HACS** (not *Settings*).
2. Top-right, click the **⋮** menu → **Custom repositories**
   (*Dépôts personnalisés*):

   ![HACS custom repositories menu](docs/images/05-hacs-custom-repo.png)

3. In the dialog, fill in:
   - **Repository**: `https://github.com/kayasax/freebox-parental-control`
   - **Type / Category**: **Integration**
   then click **Add**.
4. Close the dialog, search HACS for **Freebox Parental Control**, open it and
   click **Download**.
5. **Restart Home Assistant** when prompted
   (*Settings → System → top-right power icon → Restart*).

### Stage 2 — Add the integration

6. Go to **Settings → Devices & Services → Add Integration**, search
   **Freebox Parental Control**, and select it.
7. Keep the default address (`http://mafreebox.freebox.fr`) and submit.
8. **Walk to your Freebox**: its front LCD screen shows an authorization
   request — press the **right arrow ▶**, then **OK** to grant access. Back in
   Home Assistant, submit the second step to finish.

At this point the integration is added, but the switches will show
`insufficient_rights` until you finish Stage 3.

### Stage 3 — Grant the required rights in Freebox OS (mandatory)

Approving the request on the LCD screen only *creates* the app; by default the
Freebox gives it **minimal** rights, which are **not** enough to control
network-access. Enable the rights once:

**1. Open Freebox OS** (`http://mafreebox.freebox.fr`), then
**Paramètres de la Freebox → Gestion des accès**:

![Freebox settings – Gestion des accès](docs/images/01-gestion-des-acces.png)

**2. Open the _Applications_ tab**, find **HA Freebox Parental Control** and
click the **pencil (Éditer)** icon:

![Applications tab – edit the app](docs/images/02-applications-edit.png)

**3. Tick the required rights** — at minimum
**Modification des réglages de la Freebox**; also enable
**Accès au contrôle parental** and **Gestion des profils utilisateur** — then
**OK**:

![Rights dialog](docs/images/03-droits-acces.png)

**4. The app now lists the granted rights:**

![Granted permissions](docs/images/04-permissions-finales.png)

**5. Back in Home Assistant**, reload the integration
(**Settings → Devices & Services → Freebox Parental Control → ⋮ → Reload**).
The profile switches and device sensors appear within a minute.

## Requirements

- Home Assistant must be on the **same LAN** as the Freebox.
- A Freebox OS version exposing `network_control` (Freebox OS v15+).

## Usage

### Switches — cut / restore Internet

Each profile has a `switch.<profile>_internet`: **on = Internet allowed**, turn
it off to cut, on to restore. Use it in automations, scripts, dashboards or a
physical button.

### Device sensors — who is in each profile

Each profile has a `sensor.<profile>_devices` whose state is the device count.
Its attributes include:

- `online_count` — how many of the profile's devices are currently online;
- `device_status` — a list of `{name, online, mac}` for each assigned device;
- `devices` / `macs` — plain name and MAC lists.

A ready-made dashboard (see `dashboard_freebox_profils.json` in the repo) lists
each profile's devices with a 🟢/⚫ online indicator.

### Timed cut — `cut_for` service

To cut a profile for a bounded time with automatic restore, call the
`freebox_network_control.cut_for` service on a profile switch:

```yaml
service: freebox_network_control.cut_for
target:
  entity_id: switch.elyas_internet
data:
  minutes: 45
```

### Scheduling assistant — blueprint

Import the **"Freebox – Scheduled Internet cut for a profile"** blueprint
(`blueprints/automation/kayasax/freebox_scheduled_cut.yaml`) to cut a profile
between two times on selected days (e.g. every school night 21:00 → 07:00). In
Home Assistant this is more flexible than the Freebox's own schedule because
you can add any HA condition (presence, holidays, helpers…).

## Roadmap

- **Phase A** — switches + device sensors, config flow. ✅
- **Phase B** — per-device online status, timed cut (`cut_for`), scheduling
  blueprint. ✅
- **Phase C** — device assignment service, profile CRUD, and upstreaming async
  `network_control` / `profile` support to
  [`freebox-api`](https://github.com/hacf-fr/freebox-api).

## Credits

Built from a proven local Freebox client. Not affiliated with Free / Freebox.

## License

[MIT](LICENSE)
