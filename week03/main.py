from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'


@dataclass(frozen=True)
class LogRow:
    timestamp: datetime
    event: str
    message: str

    def to_csv_line(self) -> str:
        timestamp_str = self.timestamp.strftime(TIMESTAMP_FORMAT)
        return f'{timestamp_str},{self.event},{self.message}'


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT)


def load_log_rows(path: str) -> list[LogRow]:
    with open(path, 'r', encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != ['timestamp', 'event', 'message']:
            raise ValueError('Unexpected log header/columns.')

        rows: list[LogRow] = []
        for row in reader:
            timestamp = parse_timestamp(row['timestamp'])
            event = row['event']
            message = row['message']
            rows.append(LogRow(timestamp=timestamp, event=event, message=message))

        return rows


def is_problematic(row: LogRow) -> bool:
    message = row.message.lower()
    if 'unstable' in message:
        return True
    if 'explosion' in message:
        return True
    return False


def save_problematic_rows(path: str, rows: list[LogRow]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8', newline='') as file:
        file.write('timestamp,event,message\n')
        for row in rows:
            file.write(row.to_csv_line())
            file.write('\n')


def main() -> None:
    print('Hello Mars')

    log_path = 'week03/mission_computer_main.log'
    problematic_output_path = 'week03/mission_computer_problem.log'

    try:
        rows = load_log_rows(log_path)
    except FileNotFoundError:
        print(f'Error: file not found: {log_path}')
        return
    except PermissionError:
        print(f'Error: permission denied: {log_path}')
        return
    except ValueError as exc:
        print(f'Error: invalid log format: {exc}')
        return
    except OSError as exc:
        print(f'Error: failed to read file: {log_path} ({exc})')
        return

    print('--- ORIGINAL ORDER ---')
    print('timestamp,event,message')
    for row in rows:
        print(row.to_csv_line())

    print('--- REVERSE CHRONOLOGICAL ORDER ---')
    rows_sorted = sorted(rows, key=lambda row: row.timestamp, reverse=True)

    print('timestamp,event,message')
    for row in rows_sorted:
        print(row.to_csv_line())

    problematic_rows = [row for row in rows_sorted if is_problematic(row)]
    try:
        save_problematic_rows(problematic_output_path, problematic_rows)
    except OSError as exc:
        print(
            f'Warning: failed to write problematic log file: '
            f'{problematic_output_path} ({exc})'
        )


if __name__ == '__main__':
    main()

