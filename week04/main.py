def parse_csv_row(line: str) -> list[str]:
    parts = line.split(',')
    if len(parts) != 5:
        raise ValueError('Invalid row: expected 5 columns.')
    return [part.strip() for part in parts]


def parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def inventory_sort_key(row: list[str]) -> float:
    return parse_float(row[4])


def load_inventory_csv(csv_path: str) -> tuple[str, list[str], list[list[str]]]:
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            raw = file.read()
    except FileNotFoundError:
        print(f'Error: file not found: {csv_path}')
        return '', [], []
    except PermissionError:
        print(f'Error: permission denied: {csv_path}')
        return '', [], []
    except OSError as exc:
        print(f'Error: failed to read file: {csv_path} ({exc})')
        return '', [], []

    lines = raw.splitlines()
    if not lines:
        raise ValueError('CSV file is empty.')

    header = lines[0].strip()
    rows: list[list[str]] = []

    for line in lines[1:]:
        if not line.strip():
            continue
        try:
            row = parse_csv_row(line)
        except ValueError as exc:
            print(f'Warning: skipped a malformed row ({exc}) -> {line}')
            continue
        rows.append(row)

    return header, lines, rows


def print_csv_content(header: str, rows: list[list[str]], title: str) -> None:
    print(title)
    print(header)
    for row in rows:
        print(','.join(row))


def save_danger_csv(csv_path: str, header: str, danger_rows: list[list[str]]) -> None:
    try:
        with open(csv_path, 'w', encoding='utf-8') as file:
            file.write(header + '\n')
            for row in danger_rows:
                file.write(','.join(row) + '\n')
    except PermissionError:
        print(f'Error: permission denied: {csv_path}')
    except OSError as exc:
        print(f'Error: failed to write file: {csv_path} ({exc})')


def write_string(f, value: str) -> None:
    data = value.encode('utf-8')
    f.write(len(data).to_bytes(4, 'big'))
    f.write(data)


def read_string(data: bytes, index: int) -> tuple[str, int]:
    length = int.from_bytes(data[index:index + 4], 'big')
    index += 4
    value = data[index:index + length].decode('utf-8')
    index += length
    return value, index


def write_inventory_bin(bin_path: str, header: str, sorted_rows: list[list[str]]) -> None:
    try:
        with open(bin_path, 'wb') as file:
            write_string(file, header)
            file.write(len(sorted_rows).to_bytes(4, 'big'))
            for row in sorted_rows:
                for field in row:
                    write_string(file, field)
    except PermissionError:
        print(f'Error: permission denied: {bin_path}')
    except OSError as exc:
        print(f'Error: failed to write binary file: {bin_path} ({exc})')


def read_inventory_bin(bin_path: str) -> tuple[str, list[list[str]]]:
    try:
        with open(bin_path, 'rb') as file:
            data = file.read()
    except FileNotFoundError:
        print(f'Error: file not found: {bin_path}')
        return '', []
    except PermissionError:
        print(f'Error: permission denied: {bin_path}')
        return '', []
    except OSError as exc:
        print(f'Error: failed to read binary file: {bin_path} ({exc})')
        return '', []

    try:
        index = 0
        header, index = read_string(data, index)
        row_count = int.from_bytes(data[index:index + 4], 'big')
        index += 4

        rows: list[list[str]] = []
        for _ in range(row_count):
            row: list[str] = []
            for _ in range(5):
                field, index = read_string(data, index)
                row.append(field)
            rows.append(row)

        return header, rows
    except (IndexError, ValueError, UnicodeDecodeError) as exc:
        print(f'Error: failed to decode binary file: {bin_path} ({exc})')
        return '', []


def main() -> None:
    script_dir = __file__.rsplit('/', 1)[0]
    csv_path = script_dir + '/Mars_Base_Inventory_List.csv'
    danger_csv_path = script_dir + '/Mars_Base_Inventory_danger.csv'
    bin_path = script_dir + '/Mars_Base_Inventory_List.bin'

    header, raw_lines, rows = load_inventory_csv(csv_path)
    if not header:
        return

    if raw_lines:
        print('--- ORIGINAL CSV CONTENT ---')
        print('\n'.join(raw_lines))

    sorted_rows = sorted(rows, key=inventory_sort_key, reverse=True)
    print_csv_content(
        header,
        sorted_rows,
        '--- SORTED BY FLAMMABILITY (DESC) ---',
    )

    danger_rows: list[list[str]] = []
    for row in sorted_rows:
        if inventory_sort_key(row) >= 0.7:
            danger_rows.append(row)

    print_csv_content(
        header,
        danger_rows,
        '--- DANGEROUS (FLAMMABILITY >= 0.7) ---',
    )

    save_danger_csv(danger_csv_path, header, danger_rows)
    print(f'Saved: {danger_csv_path}')

    write_inventory_bin(bin_path, header, sorted_rows)
    print(f'Saved: {bin_path}')

    bin_header, bin_rows = read_inventory_bin(bin_path)
    if bin_header:
        print_csv_content(
            bin_header,
            bin_rows,
            '--- READ BACK FROM BINARY (SORTED) ---',
        )

    print('--- TEXT VS BINARY ---')
    print(
        '텍스트(CSV)는 사람이 읽기 쉬워 디버깅이 편하지만, 파일 크기가 더 크고 '
        '문자 파싱이 필요해서 읽기/처리가 느릴 수 있습니다.'
    )
    print(
        '이진(.bin)은 사람이 직접 읽기는 어렵지만, 정해진 형식으로 저장되어 '
        '원하는 자료를 빠르게 복원할 수 있고 일반적으로 저장 효율이 좋습니다.'
    )


if __name__ == '__main__':
    main()

