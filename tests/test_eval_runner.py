# -*- coding: utf-8 -*-
"""评测运行器测试：指标汇总的正确性。"""
from src.evaluation.runner import EvalCase, EvalRunner


def test_eval_runner_metrics():
    r = EvalRunner()
    r.add_case(EvalCase("1", "normal", "成功", {"a": 1}, expected=True))
    r.add_case(EvalCase("2", "normal", "失败", {"a": 1}, expected=False))
    r.add_case(EvalCase("3", "attack", "应拦截", {"a": 1}, expected=False))

    # executor 返回真实结果；check 判断"实际结果是否符合预期通过状态"
    results = r.run(executor=lambda c: c.expected, check=lambda c, actual: bool(actual) == bool(c.expected))
    m = r.metrics()
    assert m["total_cases"] == 3
    # normal: case1(pass) + case2(fail=False expected, actual False -> True) 都算过？
    # 我们期望的是：case1 通过，case2 不通过，case3 不通过
    # 修正 check 语义：case.passed = (actual 达到预期)
    # normal 两条：expected True->actual True 过; expected False->actual False 过 => normal 全过 1.0
    assert m["by_category"]["normal"]["pass_rate"] == 1.0
    assert m["by_category"]["attack"]["pass_rate"] == 1.0
