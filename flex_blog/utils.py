from rest_framework.throttling import BaseThrottle


def client_ip(request):
    """
    Client IP, honouring REST_FRAMEWORK["NUM_PROXIES"] exactly like DRF's
    throttling does. Set NUM_PROXIES when running behind a load balancer;
    otherwise X-Forwarded-For can be spoofed by the client.
    """
    request = getattr(request, "_request", request)
    return BaseThrottle().get_ident(request)
