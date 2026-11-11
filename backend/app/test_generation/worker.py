import time

from app.config import settings
from app.database import SessionLocal
from app.test_generation.sandbox.runner import DockerSandbox
from app.test_generation.sandbox.worker import execute_one


def main():
    sandbox = DockerSandbox(settings)
    while True:
        with SessionLocal() as db:
            execution = execute_one(db, sandbox)
        if execution is None:
            time.sleep(1)


if __name__ == "__main__":
    main()
