from config.settings import base


def test_clients_are_identified_behind_the_proxy_chain():
    assert base.REST_FRAMEWORK["NUM_PROXIES"] is not None
