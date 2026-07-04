"""Tests for PortalProfileStore."""

from src.utils.portal_profile_store import PortalProfileStore, RecordedStep, PortalProfile


def test_get_profile_missing(tmp_path):
    """get_profile returns None for unknown SSID."""
    fp = tmp_path / "test_profiles.json"
    store = PortalProfileStore(data_file=str(fp))
    assert store.get_profile("UnknownNet") is None
    assert store.has_profile("UnknownNet") is False


def test_save_and_retrieve(tmp_path):
    """save_profile then get_profile returns the profile."""
    fp = tmp_path / "test_profiles.json"
    store = PortalProfileStore(data_file=str(fp))
    steps = [
        RecordedStep(type="click", selector="#agree", text="同意"),
        RecordedStep(type="fill", selector="#username", value="user"),
    ]
    store.save_profile("TestNet", steps)

    profile = store.get_profile("TestNet")
    assert profile is not None
    assert profile.ssid == "TestNet"
    assert len(profile.steps) == 2
    assert profile.steps[0].selector == "#agree"
    assert profile.replay_count == 0


def test_has_profile(tmp_path):
    """has_profile returns True after save."""
    fp = tmp_path / "test_profiles.json"
    store = PortalProfileStore(data_file=str(fp))
    assert store.has_profile("TestNet") is False
    store.save_profile("TestNet", [RecordedStep(type="click", selector="#ok")])
    assert store.has_profile("TestNet") is True


def test_persistence(tmp_path):
    """Profiles survive save/load cycle via disk."""
    fp = tmp_path / "test_profiles.json"
    steps = [
        RecordedStep(type="click", selector="#agree", text="Accept"),
        RecordedStep(type="fill", selector="#name", value="test"),
        RecordedStep(type="fill", selector="#pwd", value="<SECURE_CREDENTIAL>", is_password=True),
    ]
    store1 = PortalProfileStore(data_file=str(fp))
    store1.save_profile("PersistNet", steps)
    store1.record_replay_result("PersistNet", True)
    del store1

    store2 = PortalProfileStore(data_file=str(fp))
    profile = store2.get_profile("PersistNet")
    assert profile is not None
    assert len(profile.steps) == 3
    assert profile.steps[2].is_password is True
    assert profile.replay_count == 1
    assert profile.replay_success_count == 1


def test_corrupt_json(tmp_path):
    """Corrupt JSON does not crash — starts with empty records."""
    fp = tmp_path / "test_profiles.json"
    fp.write_text("{{{", encoding="utf-8")
    store = PortalProfileStore(data_file=str(fp))
    assert store.get_profile("Any") is None


