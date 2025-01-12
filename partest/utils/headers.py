class ContentHeaders:
    DEFAULT_HEADERS = {
        'Content-Type': 'application/json',
        'Content-Type': 'text/html',
        'Content-Type': 'multipart/form-data'
    }

    @staticmethod
    def get_headers():
        return ContentHeaders.DEFAULT_HEADERS

    @staticmethod
    def json_headers():
        headers = ContentHeaders.DEFAULT_HEADERS.copy()
        headers['Content-Type'] = 'application/json'
        return headers

    @staticmethod
    def html_headers():
        headers = ContentHeaders.DEFAULT_HEADERS.copy()
        headers['Content-Type'] = 'text/html'
        return headers

    @staticmethod
    def form_data_headers():
        headers = ContentHeaders.DEFAULT_HEADERS.copy()
        headers['Content-Type'] = 'multipart/form-data'
        return headers