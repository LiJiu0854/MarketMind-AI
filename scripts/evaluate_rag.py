"""Run explicitly approved live RAG evaluation against one knowledge base."""

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.services.knowledge import get_knowledge_base
from app.services.rag_evaluation import (
    EvaluationCase,
    EvaluationReport,
    load_evaluation_cases,
    run_evaluation,
)


def positive_id(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("知识库 ID 必须为正整数") from None
    if result <= 0:
        raise argparse.ArgumentTypeError("知识库 ID 必须为正整数")
    return result


async def run_live_evaluation(base_id: int, cases: list[EvaluationCase]) -> EvaluationReport:
    settings = Settings()
    if settings.database_url is None:
        raise ValueError("数据库配置缺失")
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            base = await get_knowledge_base(session, base_id)
            session.expunge(base)
            await session.rollback()
            return await run_evaluation(session, base, cases, settings)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG 知识库质量评估（可能产生模型费用）")
    parser.add_argument("--knowledge-base-id", type=positive_id, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="明确允许连接模型与向量服务")
    args = parser.parse_args(argv)
    if not args.live:
        parser.print_usage()
        print("必须显式传入 --live；未发起任何模型或向量服务请求。")
        return 2
    try:
        if args.cases.resolve() == args.output.resolve():
            raise ValueError("输入与输出路径不能相同")
        cases = load_evaluation_cases(args.cases)
        report = asyncio.run(run_live_evaluation(args.knowledge_base_id, cases))
        args.output.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError):
        print("评估无法完成：请检查用例、输出路径和服务配置；没有输出敏感详情。")
        return 1
    except Exception:
        print("评估服务不可用；没有输出提供商或数据库异常详情。")
        return 1
    print(f"评估完成：{report.case_count} 条，失败 {report.failure_count} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
