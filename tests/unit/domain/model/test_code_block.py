from standards_atlas.domain.model import CodeBlock, render_content_as_plain_text


def test_code_block_plain_text_preserves_formatting() -> None:
    code = "if value:\n    return  value"
    block = CodeBlock(id="code", code=code, language="python")
    assert render_content_as_plain_text((block,)) == code
    assert CodeBlock.model_validate_json(block.model_dump_json()) == block
