# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from core import cleaner, i18n, packages, power, services


def test_validate_unit_name_ok() -> None:
    assert services.validate_unit_name("sshd") == "sshd.service"
    assert services.validate_unit_name("sshd.service") == "sshd.service"
    assert services.validate_unit_name("user@1000") == "user@1000.service"


def test_validate_unit_name_rejects() -> None:
    with pytest.raises(services.ServiceError):
        services.validate_unit_name("../evil")
    with pytest.raises(services.ServiceError):
        services.validate_unit_name("a;b")
    with pytest.raises(services.ServiceError):
        services.validate_unit_name("")


def test_allowed_service_actions() -> None:
    assert "restart" in services.ALLOWED_ACTIONS
    assert "rm" not in services.ALLOWED_ACTIONS


def test_validate_pkg_id() -> None:
    assert packages._validate_pkg_id("htop") == "htop"
    assert packages._validate_pkg_id("org.gnome.Calculator") == "org.gnome.Calculator"
    with pytest.raises(packages.PackageError):
        packages._validate_pkg_id("../x")
    with pytest.raises(packages.PackageError):
        packages._validate_pkg_id("a b")


def test_allowed_governors() -> None:
    assert "performance" in power.ALLOWED_GOVERNORS
    with pytest.raises(power.PowerError):
        power.set_governor("not-a-governor")  # fails validation before pkexec


def test_power_profile_name() -> None:
    assert power.re_sub_profile("balanced") == "balanced"
    with pytest.raises(power.PowerError):
        power.re_sub_profile("bad;rm")


def test_cleaner_rejects_unknown_targets() -> None:
    with pytest.raises(cleaner.CleanerError):
        cleaner.clean(["not_a_real_target"])


def test_cleaner_whitelist_paths_keys() -> None:
    known = set(cleaner.TARGET_DEFS)
    paths = cleaner._whitelist_paths()
    assert known <= set(paths) | known  # all targets defined
    for key in known:
        assert key in paths


def test_i18n_key_parity() -> None:
    fr = set(i18n._STRINGS["fr"])
    en = set(i18n._STRINGS["en"])
    assert fr == en, f"missing in en: {fr - en}; missing in fr: {en - fr}"


def test_i18n_t_format() -> None:
    i18n.set_language("fr")
    text = i18n.t("update_up_to_date", version="1.2.3")
    assert "1.2.3" in text
    i18n.set_language("en")
    text = i18n.t("update_up_to_date", version="1.2.3")
    assert "1.2.3" in text
