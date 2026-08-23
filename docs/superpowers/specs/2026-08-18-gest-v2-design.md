# Hub Système 2.0 — design

**Date:** 2026-08-18  
**Promesse:** cockpit dans une seule fenêtre — commande visible, flux live, une action à la fois, cliché avant le risque. Score santé sur le tableau de bord. Canal Flatpak prêt Flathub (métadonnées + source publique).

## Non-négociable

- Toujours 100 % local sauf vérif MAJ GitHub (allowlist inchangée).
- Canal utilisateur = Flatpak (`linux-flatpak-releases`). Pas de native publique.
- Pas de rewrite Qt/web. GTK4 / Libadwaita / pont `flatpak-spawn --host` + `pkexec`.
- `flock` paquets 1.4.13 conservé. Corps `pacman`/`apt`/`dnf`/`flatpak`/`snap` inchangé.
- Pas de `shell=True`. Scripts uniquement sous `updates_dir()`.

## 1. Console live in-app (paquets)

Les boutons Paquets **Vérifier** / **Tout mettre à jour** n’ouvrent plus Konsole.

- `core/jobs.py` lance le script existant via `host.popen` (wrap Flatpak). Si `script` (util-linux) est là : PTY (`script -qefc`) pour débuffer pacman.
- `ui/job_console.py` : fenêtre transitoire, `Gtk.TextView` monospace, stream stdout, fermeture bloquée tant que le process tourne (ne pas tuer `pacman -Syu`).
- Dialogue d’apply : toujours la liste des gestionnaires réellement lancés (`host_manager_labels`).
- Repli : si spawn échoue → `open_terminal_script` (Konsole) comme 1.4.13.

**Exception MAJ Gest :** le script Flatpak relance l’app et l’ancienne instance doit quitter. La console in-app mourrait. Conservé : process détaché (Konsole / terminal). En revanche, « déjà à jour » / erreur = toast, pas de terminal ; une MAJ dispo = dialogue GTK existant puis terminal d’install.

## 2. Cliché avant le risque

Avant **Tout mettre à jour** (paquets), si Snapper ou Timeshift est détecté :

1. Le dialogue le dit.
2. `backup.create_snapshot("Hub Système: avant MAJ paquets")` (pkexec).
3. Échec ou annulation polkit → **pas** d’upgrade.
4. Succès → console apply.

Pas de cliché automatique sur restore (c’est déjà un rollback) ni sur le nettoyeur (réversible / caches).

## 3. Score santé

`core/health.evaluate(metrics, settings)` → `{score: 0..100, grade: A|B|C|D, items, recommendations}`.

Pénalités (mêmes seuils que les alertes) : CPU 25, RAM 25, disque 20, température 20. Extra : swap ≥ 50 % → 10 ; load1 > 2× cœurs logiques → 10 ; batterie < 15 % débranchée → 5.

UI : ligne « Santé » en tête du hero dashboard. Clic → dialogue des reco (page cible).

Pas de pkexec au tick monitoring.

## 4. Flathub

On ne peut pas fusionner un PR Flathub sans compte. 2.0 livre :

- AppStream : categories, keywords, developer, description V2.
- `packaging/FLATHUB.md` : `--filesystem=host` + `talk-name=org.freedesktop.Flatpak` assumés (outil système) ; source **tar.gz public** à côté du `.flatpak` (GPL + build Flathub).
- Pas de garantie d’acceptation Flathub (permissions hôte).

## Fichiers

| Nouveau | Rôle |
|---|---|
| `core/health.py` | Score pur |
| `core/jobs.py` | argv + spawn script updates/ |
| `ui/job_console.py` | Fenêtre live |
| `packaging/FLATHUB.md` | Dossier soumission |
| `docs/superpowers/specs/2026-08-18-gest-v2-design.md` | Ce spec |

## Hors 2.0.0

- VTE embarqué, découpe complète de `MainWindow`, plugins, AUR, rewrite MAJ Gest in-app.
