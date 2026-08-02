# AGENTS.md

## Project Mission

This project is a practical training ground for programmers who want to reach the 10 million yen income level by improving real systems.

The goal is not to write code that merely works. The goal is to turn working code into code that is fast, cheap to operate, stable, scalable, and maintainable under real business pressure.

## Core Principle

Turn "it works for now" code into code that continues to work correctly when data volume, users, cost pressure, and operational risk increase by orders of magnitude.

## What This Project Values

- Preserve existing external behavior before optimizing internals.
- Measure bottlenecks before changing performance-sensitive code.
- Improve algorithmic complexity, I/O count, API call count, memory use, and concurrency behavior.
- Prefer simple, robust designs that fail safely.
- Keep business requirements, operating cost, scale, and recovery paths visible when making technical decisions.
- Explain changes in terms of speed, cost, correctness, reliability, and scalability.

## Agent Rules

- Read the existing code and workflow before editing.
- Identify inputs, outputs, side effects, and failure modes before changing behavior.
- Do not hard-code API keys, tokens, credentials, or secrets.
- Keep external interfaces compatible unless the user explicitly asks for a breaking change.
- When optimizing, use the sequence: measure, hypothesize, modify, verify.
- Prioritize high-impact bottlenecks such as nested loops, repeated I/O, repeated API calls, synchronous waits, unnecessary serialization, and memory-heavy processing.
- Prefer batch processing, caching, streaming, asynchronous processing, parallel execution, and serverless scaling when they fit the workload.
- Add logs that help diagnose production failures without leaking secrets or private data.
- Make changes small enough to review, test, and roll back.

## Target Skills

- Algorithms and computational complexity
- Data structures
- Runtime behavior and memory use
- Database and file I/O optimization
- API cost optimization
- Batch processing
- Async and parallel processing
- Caching
- Cloud architecture
- Serverless scaling
- Observability and logging
- Failure recovery
- Business-aware technical design

## Development Style

First understand the existing system. Then protect its behavior. Then improve the implementation.

For each meaningful change, record what was slow, expensive, unstable, or risky, and why the new version is better.

Code quality matters, but the larger goal is business-level leverage: handling more users, more records, more traffic, and more operational risk with less cost and fewer failures.
