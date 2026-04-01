import random
from datetime import datetime

LOG_FILE_NAME = 'mars_sensor_log.txt'


def _log_file_path() -> str:
    normalized = __file__.replace('\\', '/')
    if '/' in normalized:
        directory = normalized.rsplit('/', 1)[0]
        return f'{directory}/{LOG_FILE_NAME}'
    return LOG_FILE_NAME


class DummySensor:
    def __init__(self) -> None:
        self.env_values = {
            'mars_base_internal_temperature': 0.0,
            'mars_base_external_temperature': 0.0,
            'mars_base_internal_humidity': 0.0,
            'mars_base_external_illuminance': 0.0,
            'mars_base_internal_co2': 0.0,
            'mars_base_internal_oxygen': 0.0,
        }

    def set_env(self) -> None:
        self.env_values['mars_base_internal_temperature'] = random.uniform(18, 30)
        self.env_values['mars_base_external_temperature'] = random.uniform(0, 21)
        self.env_values['mars_base_internal_humidity'] = random.uniform(50, 60)
        self.env_values['mars_base_external_illuminance'] = random.uniform(500, 715)
        self.env_values['mars_base_internal_co2'] = random.uniform(0.02, 0.1)
        self.env_values['mars_base_internal_oxygen'] = random.uniform(4, 7)

    def get_env(self) -> dict[str, float]:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ev = self.env_values
        line = (
            f'{timestamp},'
            f"{ev['mars_base_internal_temperature']},"
            f"{ev['mars_base_external_temperature']},"
            f"{ev['mars_base_internal_humidity']},"
            f"{ev['mars_base_external_illuminance']},"
            f"{ev['mars_base_internal_co2']},"
            f"{ev['mars_base_internal_oxygen']}\n"
        )
        try:
            with open(_log_file_path(), 'a', encoding='utf-8') as log_file:
                log_file.write(line)
        except PermissionError:
            print(f'Error: permission denied writing log: {_log_file_path()}')
        except OSError as exc:
            print(f'Error: failed to write log: {_log_file_path()} ({exc})')

        return self.env_values


if __name__ == '__main__':
    ds = DummySensor()
    ds.set_env()
    env = ds.get_env()
    print('DummySensor env_values:')
    for key in sorted(env.keys()):
        print(f'  {key}: {env[key]}')
