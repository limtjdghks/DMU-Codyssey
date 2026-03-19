def parse_log_line(line: str) -> tuple[str, str, str]:
    parts = line.split(',', 2)
    if len(parts) != 3:
        raise ValueError('Invalid log line format.')
    timestamp = parts[0].strip()
    event = parts[1].strip()
    message = parts[2].strip()
    return timestamp, event, message


def load_log_rows(path: str) -> list[tuple[str, str, str]]:
    with open(path, 'r', encoding='utf-8') as file:
        lines = file.read().splitlines()

    if not lines:
        raise ValueError('Log file is empty.')

    header = lines[0].strip()
    if header != 'timestamp,event,message':
        raise ValueError('Unexpected log header/columns.')

    rows: list[tuple[str, str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        rows.append(parse_log_line(line))
    return rows


def to_csv_line(row: tuple[str, str, str]) -> str:
    timestamp, event, message = row
    return f'{timestamp},{event},{message}'


def is_problematic(row: tuple[str, str, str]) -> bool:
    message = row[2].lower()
    if 'unstable' in message:
        return True
    if 'explosion' in message:
        return True
    return False


def save_problematic_rows(path: str, rows: list[tuple[str, str, str]]) -> None:
    with open(path, 'w', encoding='utf-8') as file:
        file.write('timestamp,event,message\n')
        for row in rows:
            file.write(to_csv_line(row))
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
        print(to_csv_line(row))

    print('--- REVERSE CHRONOLOGICAL ORDER ---')
    rows_sorted = sorted(rows, key=lambda row: row[0], reverse=True)

    print('timestamp,event,message')
    for row in rows_sorted:
        print(to_csv_line(row))

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

