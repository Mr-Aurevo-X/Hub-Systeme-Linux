# Packaging Hub Système

- `packaging/build-flatpak.sh` → `dist/org.mraurevox.HubSysteme.flatpak`
- `packaging/publish-flatpak-release.sh` → release `vX.Y.Z` sur **Hub-Systeme-Linux** uniquement
- `packaging/sync-public-readmes.sh` : LEGAL sur les hubs CT (`linux-releases`, `linux-flatpak-releases`) — **pas** de release Hub Système sur ces hubs
- Templates hub CT : `public-readme-flatpak.md.in`, `public-readme-native.md.in` (référence ; sync README depuis crypto-tracker)

**Flatpak uniquement** (`Hub-Systeme-Linux/releases`). `install.sh` n’est plus l’install utilisateur. Ne pas publier sur `Mr-Aurevo-X/Hub-Systeme` (hub Windows).
