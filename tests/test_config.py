import pytest

from marginalis import config


def test_splits_are_contiguous_and_cover_study_window():
    assert config.SPLITS[0].start == config.DATA_START
    assert config.SPLITS[-1].end == config.DATA_END
    for a, b in zip(config.SPLITS, config.SPLITS[1:]):
        assert a.end == b.start


def test_holdout_refused_until_frozen():
    assert config.require_split(config.TRAIN) is config.TRAIN
    if not config.METHOD_FROZEN:
        for split in (config.HOLDOUT, config.HOLDOUT_YTD):
            with pytest.raises(config.HeldOutDataError):
                config.require_split(split)


def test_ba_build_order():
    assert list(config.BAS) == ["ERCO", "CISO", "MISO"]


def test_holdout_allowed_once_frozen():
    if config.METHOD_FROZEN:
        assert config.require_split(config.HOLDOUT) is config.HOLDOUT
        assert config.require_split(config.HOLDOUT_YTD) is config.HOLDOUT_YTD
