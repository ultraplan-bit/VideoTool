"""转换作业模型。

一个作业 = 一个源文件 + 一个预设 + 一个输出路径。
作业队列负责顺序执行、状态流转和整体进度统计。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(Enum):
    PENDING = "等待中"
    RUNNING = "转换中"
    DONE = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"

    @property
    def is_final(self) -> bool:
        return self in (Status.DONE, Status.FAILED, Status.CANCELLED)


_ids = itertools.count(1)


@dataclass
class Job:
    source: str
    preset_key: str
    preset_label: str
    quality: str
    output: str
    encoder: str | None = None      # 硬件编码器名；None 表示用预设的软件编码器
    duration: float | None = None
    status: Status = Status.PENDING
    progress: float = 0.0
    message: str = ""
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def name(self) -> str:
        return Path(self.source).name


class Queue:
    """按加入顺序执行的作业队列。"""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.current: Job | None = None
        self.cancelled = False

    def __len__(self) -> int:
        return len(self.jobs)

    def add(self, job: Job) -> None:
        self.jobs.append(job)

    def clear_finished(self) -> int:
        """移除所有已结束的作业，返回移除数量。"""
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if not j.status.is_final]
        return before - len(self.jobs)

    def remove(self, job: Job) -> None:
        if job in self.jobs and job.status is not Status.RUNNING:
            self.jobs.remove(job)

    def next_pending(self) -> Job | None:
        if self.cancelled:
            return None
        return next((j for j in self.jobs if j.status is Status.PENDING), None)

    def mark_cancelled_pending(self) -> None:
        """取消后把还没开始的作业标记掉，避免状态栏一直显示等待。"""
        for job in self.jobs:
            if job.status is Status.PENDING:
                job.status = Status.CANCELLED
                job.message = "已取消"

    @property
    def counts(self) -> dict[str, int]:
        summary = {"total": len(self.jobs), "done": 0, "failed": 0, "pending": 0}
        for job in self.jobs:
            if job.status is Status.DONE:
                summary["done"] += 1
            elif job.status is Status.FAILED:
                summary["failed"] += 1
            elif job.status in (Status.PENDING, Status.RUNNING):
                summary["pending"] += 1
        return summary

    @property
    def overall_progress(self) -> float:
        """整体进度：按已完成作业数 + 当前作业进度折算。"""
        if not self.jobs:
            return 0.0
        done = sum(
            1.0 if j.status is Status.DONE else j.progress
            for j in self.jobs
            if j.status in (Status.DONE, Status.RUNNING, Status.FAILED, Status.CANCELLED)
        )
        return min(done / len(self.jobs), 1.0)

    def output_taken(self, path: str) -> bool:
        """输出路径是否已被队列里的作业占用。"""
        target = str(Path(path).resolve()).lower()
        return any(
            str(Path(j.output).resolve()).lower() == target
            for j in self.jobs
            if not j.status.is_final
        )
