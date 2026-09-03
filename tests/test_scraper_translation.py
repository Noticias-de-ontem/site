from unittest import mock

import scraper


def test_translate_caption_uses_http_response_segments():
    response = mock.Mock()
    response.json.return_value = [[["Translated ", "Traduzido "], ["caption", "texto"]]]

    with mock.patch.object(scraper.requests, "get", return_value=response) as get:
        result = scraper.translate_caption_if_needed(
            "Texto em português",
            "en",
            "geopoliticahoje",
        )

    assert result == "Translated caption"
    response.raise_for_status.assert_called_once_with()
    assert get.call_args.kwargs["timeout"] == 20


def test_translate_caption_keeps_original_on_invalid_response():
    response = mock.Mock()
    response.json.return_value = []

    with mock.patch.object(scraper.requests, "get", return_value=response):
        result = scraper.translate_caption_if_needed(
            "Texto original",
            "en",
            "geopoliticahoje",
        )

    assert result == "Texto original"
