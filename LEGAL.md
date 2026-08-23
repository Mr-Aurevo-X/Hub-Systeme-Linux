<!-- lang:fr -->
# Mentions légales — Hub Système

**Copyright © 2026 Mr-Aurevo-X.** Tous droits réservés sur le nom, les marques et les visuels.

Le code source est un logiciel libre sous licence [GPL-3.0-or-later](LICENSE).

## Conditions d’utilisation (CGU)

1. Hub Système est un utilitaire d’administration **locale** de votre machine Linux.
2. Le logiciel est fourni « en l’état », sans garantie d’aucune sorte (GPL §15–16).
3. Vous êtes seul responsable des actions privilégiées (pkexec, services, pare-feu, clichés, paquets, plugins).
4. Usage autorisé : personnel ou professionnel sur des systèmes que vous administrez légitimement.
5. Toute copie ou redistribution doit respecter la GPL-3.0-or-later.

## Vie privée (RGPD)

Mr-Aurevo-X **ne collecte aucune donnée personnelle**. Pas de compte, pas de télémétrie, pas de publicité, pas de revente.

- Stockage local uniquement : `~/.config/hub-systeme/` (préférences, `fleet.json`) et `~/.local/share/hub-systeme/` (cache de mises à jour, plugins).
- Pas de traitement par l’éditeur : vous restez maître des fichiers sur votre disque (suppression = désinstallation ou effacement de ces dossiers).
- **Exception :** si la vérification des mises à jour est activée, une requête HTTPS est envoyée à GitHub (`api.github.com`, dépôt public `Gest_Linux_Pro`). GitHub peut voir l’adresse IP et le User-Agent selon **sa** politique. Ce n’est pas un profilage par Mr-Aurevo-X. Désactivable dans Préférences.
- Pas de cookies, pas de sous-traitant de l’éditeur hors GitHub pour ce check.
- **Connexions (page Réseau) :** lecture **locale** de la table de sockets de **cette** machine (`ss` sur l’hôte, éventuellement via pkexec pour les PIDs). Adresses IP et ports restent sur votre disque (liste « connu » dans `settings.json`). **Aucun envoi**, pas de reverse DNS, pas de réputation en ligne, pas de coupure/blocage de flux.
- **Fiche / Parc :** inventaire local et liste de machines que **vous** saisissez (`fleet.json`). Sondes TCP/ICMP depuis cette machine uniquement. Pas de WOL, pas de mot de passe stocké, pas d’agent.

Contact : issues GitHub du projet.

<!-- lang:en -->
# Legal notice — Hub Système

**Copyright © 2026 Mr-Aurevo-X.** All rights reserved on the name, marks, and artwork.

Source code is free software under [GPL-3.0-or-later](LICENSE).

## Terms of use

1. Hub Système is a **local** Linux system-administration utility.
2. The software is provided “as is”, without warranty of any kind (GPL §§15–16).
3. You are solely responsible for privileged actions (pkexec, services, firewall, snapshots, packages, plugins).
4. Permitted use: personal or professional on systems you legitimately administer.
5. Any copy or redistribution must follow GPL-3.0-or-later.

## Privacy (GDPR)

Mr-Aurevo-X **collects no personal data**. No account, no telemetry, no ads, no resale.

- Local storage only: `~/.config/hub-systeme/` (preferences, `fleet.json`) and `~/.local/share/hub-systeme/` (update cache, plugins).
- No processing by the publisher: you control files on your disk (delete those folders or uninstall).
- **Exception:** if update checks are enabled, an HTTPS request is sent to GitHub (`api.github.com`, public `Gest_Linux_Pro`). GitHub may see your IP and User-Agent under **its** policy. This is not profiling by Mr-Aurevo-X. Can be disabled in Preferences.
- No cookies; no publisher processors besides GitHub for that check.
- **Connections (Network page):** **local** read of **this** machine’s socket table (`ss` on the host, optionally via pkexec for PIDs). IP addresses and ports stay on your disk (“known” list in `settings.json`). **No upload**, no reverse DNS, no online reputation, no kill/block of flows.
- **Machine sheet / Fleet:** local inventory and machines **you** type (`fleet.json`). TCP/ICMP probes from this machine only. No WOL, no stored passwords, no agent.

Contact: project GitHub issues.
