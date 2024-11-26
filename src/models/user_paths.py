class PathsServices:

    services_paths = {
        'article': {
            'service_path_v1': ['/v1/article'],
            'service_endpoints_path': {
                'general_path': {
                    'url': '',
                    'methods': ['GET', 'POST', 'PATCH', 'DELETE']
                }
            }
        },
        'health_check': {
            'service_path_v1': '/_health',
            'service_endpoints_path': {
                'general_path': {
                    'url': '',
                    'methods': ['GET']
                },
            }
        }
    }


