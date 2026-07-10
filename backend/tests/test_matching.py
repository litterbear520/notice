from app.matching import find_matches


def test_matches_in_title():
    assert find_matches("部分老旧模型下线通知", "", ["模型", "下线", "qwen"]) == ["模型", "下线"]


def test_matches_in_content_case_insensitive():
    assert find_matches("公告", "Qwen-Max is DEPRECATED", ["qwen", "deprecat"]) == ["qwen", "deprecat"]


def test_no_match_returns_empty():
    assert find_matches("数据库价格调整", "RDS 优惠", ["模型", "下线"]) == []


def test_empty_keywords():
    assert find_matches("模型下线", "内容", []) == []
