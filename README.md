# Hub Système (Linux)

> **WIP** — encore en développement.  
> **WIP** — still in development.

Hub GTK 4 autonome — santé, processus, paquets, disques, journaux (ex-Gest). **Linux uniquement** — distinct du Hub Système Windows (PC Command).

**1.1.4** — [releases](https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases) · GPL-3.0-or-later · © 2026 Mr-Aurevo-X

---

## Français

### Installer (Flatpak)

Prérequis : [Flatpak](https://flatpak.org/setup/) + runtime GNOME 49 (installé automatiquement depuis Flathub au premier `flatpak install`).

```bash
rm -f org.mraurevox.HubSysteme.flatpak
wget --no-continue -O org.mraurevox.HubSysteme.flatpak \
  https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/v1.1.4/org.mraurevox.HubSysteme.flatpak
flatpak install --user -y --reinstall ./org.mraurevox.HubSysteme.flatpak
wget --no-continue -O INSTALLER-RACCOURCI-FLATPAK.sh \
  https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/v1.1.4/INSTALLER-RACCOURCI-FLATPAK.sh
bash ./INSTALLER-RACCOURCI-FLATPAK.sh
flatpak run org.mraurevox.HubSysteme
```

Dev sans installer : `bash LANCER.sh`

### Ce que ça fait

- Tableau de bord et fiche machine
- Processus, services, autostart, timers
- Paquets, nettoyeur, usage disque
- Journaux, outils, sauvegardes, sessions

### Ce que ça ne fait pas

Pas de télémétrie, pas d’install automatique, pas de canal Flathub.  
La vérif. GitHub n’affiche que des commandes à copier-coller.

### Confidentialité

Local-first. Données : `~/.config/Mr-Aurevo-X/hubs/systeme/` · `~/.local/share/hub-systeme/`.  
Vérif. versions GitHub au démarrage (désactivable).  
Texte : [LEGAL.md](LEGAL.md) — dans l’app : Préférences → Mentions légales.

---

## English

Standalone GTK 4 hub — health, processes, packages, disks, logs (ex-Gest). **Linux only** — separate from the Windows System Hub (PC Command).

### Install (Flatpak)

```bash
rm -f org.mraurevox.HubSysteme.flatpak
wget --no-continue -O org.mraurevox.HubSysteme.flatpak \
  https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/v1.1.4/org.mraurevox.HubSysteme.flatpak
flatpak install --user -y --reinstall ./org.mraurevox.HubSysteme.flatpak
wget --no-continue -O INSTALLER-RACCOURCI-FLATPAK.sh \
  https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/v1.1.4/INSTALLER-RACCOURCI-FLATPAK.sh
bash ./INSTALLER-RACCOURCI-FLATPAK.sh
flatpak run org.mraurevox.HubSysteme
```

Dev without install: `bash LANCER.sh`

No telemetry, no auto-install. Not on Flathub — GitHub Releases only.

Privacy: local-first. Data under `~/.config/Mr-Aurevo-X/hubs/systeme/`. Startup GitHub version check (can be disabled). See [LEGAL.md](LEGAL.md).

---

## Soutien (optionnel) / Support (optional)

Si le boulot te plaît, un café — sinon profite.  
If you like the work, a coffee — otherwise just enjoy it.

[![Discord](https://img.shields.io/badge/Discord-Mr--Aurevo--X-5865F2?style=for-the-badge&logo=discord&logoColor=white&labelColor=050807)](https://discord.com/users/406891052516114442)

---

Copyright © 2026 Mr-Aurevo-X — GPL-3.0-or-later
