from costci.providers import CAPABILITIES, METHODS

CLASSES = {"DIRECTLY_MEASURED", "DERIVED", "ESTIMATED", "UNAVAILABLE"}


def test_every_provider_declares_every_method():
    for provider, caps in CAPABILITIES.items():
        assert set(caps) == set(METHODS), provider


def test_classifications_are_from_the_phase1_vocabulary():
    for provider, caps in CAPABILITIES.items():
        for method, (primitive, cls) in caps.items():
            assert cls in CLASSES, (provider, method, cls)
            assert primitive.strip(), (provider, method)


def test_no_platform_has_a_pre_execution_time_estimate():
    # Phase 1 finding: static signals on real platforms are bytes/partitions/statistics, never time or $.
    for provider in ("snowflake", "bigquery", "databricks"):
        assert CAPABILITIES[provider]["static_signals"][1] == "ESTIMATED"
