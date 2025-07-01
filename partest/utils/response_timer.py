from functools import wraps
import time

stats = {}

def measure_response_time(endpoint_name, num_tests=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            api_client = kwargs.get('api_client')
            if api_client is None:
                raise ValueError("api_client не найден в аргументах теста")

            original_make_request = api_client.make_request

            async def wrapped_make_request(*mr_args, **mr_kwargs):
                start_time = time.time()
                response = await original_make_request(*mr_args, **mr_kwargs)
                end_time = time.time()
                elapsed_time = end_time - start_time

                if endpoint_name not in stats:
                    stats[endpoint_name] = []
                stats[endpoint_name].append(elapsed_time)
                return response

            api_client.make_request = wrapped_make_request
            result = await func(*args, **kwargs)
            api_client.make_request = original_make_request
            return result
        return wrapper
    return decorator