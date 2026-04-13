def log_case_result(case_id, scenario, expected, actual):
    print(f"[CASE] {case_id}")
    print(f"  scenario : {scenario}")
    print(f"  expected : {expected}")
    print(f"  actual   : {actual}")


def assert_case(case_id, scenario, expected, actual, passed):
    log_case_result(case_id, scenario, expected, actual)
    print(f"  result   : {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise AssertionError(
            f"{case_id} failed\n"
            f"scenario={scenario}\n"
            f"expected={expected}\n"
            f"actual={actual}"
        )

