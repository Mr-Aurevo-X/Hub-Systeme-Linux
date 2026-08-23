# Hub Système - empaquetage
APP_NAME := Gest_Linux_Pro
VERSION  := $(shell tr -d '[:space:]' < VERSION 2>/dev/null || echo 1.0.0)
DIST_DIR := dist
TARBALL  := $(DIST_DIR)/$(APP_NAME)-$(VERSION).tar.gz
DEB      := $(DIST_DIR)/hub-systeme_$(VERSION)_all.deb

.PHONY: help dist deb flatpak clean version

help:
	@echo "Cibles :"
	@echo "  make dist     -> $(TARBALL)"
	@echo "  make deb      -> $(DEB) (Debian/Ubuntu, via packaging/build-deb.sh)"
	@echo "  make flatpak  -> dist/org.mraurevox.HubSysteme-$(VERSION).flatpak + asset public"
	@echo "  make clean    -> nettoie dist/"
	@echo "  make version  -> affiche la version"

version:
	@echo $(VERSION)

dist:
	@mkdir -p $(DIST_DIR)
	@rm -f $(TARBALL)
	tar -czf $(TARBALL) \
		--exclude='.git' \
		--exclude='.cursor' \
		--exclude='venv' \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='dist' \
		--exclude='.pytest_cache' \
		--transform 's,^\./,$(APP_NAME)-$(VERSION)/,' \
		./VERSION ./LICENSE ./COPYRIGHT ./LEGAL.md ./README.md ./requirements.txt ./main.py \
		./install.sh ./uninstall.sh ./LANCER.sh ./INSTALLER-RACCOURCI.sh ./INSTALLER-RACCOURCI-FLATPAK.sh \
		./Hub-Systeme.desktop ./Makefile ./MANIFEST \
		./core ./ui ./ui_kit ./packaging ./docs
	@echo "OK -> $(TARBALL)"
	@ls -lh $(TARBALL)

deb:
	bash packaging/build-deb.sh

flatpak:
	bash packaging/build-flatpak.sh

clean:
	rm -rf $(DIST_DIR)/deb-stage $(DIST_DIR)/flatpak-build $(DIST_DIR)/flatpak-repo
	rm -f $(DIST_DIR)/$(APP_NAME)-*.tar.gz $(DIST_DIR)/$(APP_NAME)-*.tar.gz.sha256
	rm -f $(DIST_DIR)/hub-systeme_*.deb
	rm -f $(DIST_DIR)/org.mraurevox.HubSysteme-*.flatpak
	rm -f $(DIST_DIR)/org.mraurevox.HubSysteme.flatpak
