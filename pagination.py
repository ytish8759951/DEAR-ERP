def get_page_args(request, default_page_size=50, allowed_page_sizes=(50, 100, 200)):
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1

    try:
        per_page = int(request.args.get("per_page", str(default_page_size)))
    except ValueError:
        per_page = default_page_size

    if per_page not in allowed_page_sizes:
        per_page = default_page_size

    return max(page, 1), per_page


def pagination_context(pagination):
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_prev": pagination.has_prev,
        "has_next": pagination.has_next,
        "prev_num": pagination.prev_num,
        "next_num": pagination.next_num,
    }
