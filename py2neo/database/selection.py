#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# Copyright 2011-2016, Nigel Small
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from py2neo.database.cypher import cypher_escape


def _property_equality_conditions(properties, offset=1):
    for i, (key, value) in enumerate(properties.items(), start=offset):
        if key == "__id__":
            condition = "id(_)"
        else:
            condition = "_.%s" % cypher_escape(key)
        if isinstance(value, (tuple, set, frozenset)):
            condition += " IN {%d}" % i
            parameters = {"%d" % i: list(value)}
        else:
            condition += " = {%d}" % i
            parameters = {"%d" % i: value}
        yield condition, parameters


class NodeSelection(object):
    """ An immutable set of node selection criteria.
    """

    def __init__(self, graph, labels=frozenset(), conditions=tuple(), order_by=tuple(), skip=None, limit=None):
        self.graph = graph
        self._labels = frozenset(labels)
        self._conditions = tuple(conditions)
        self._order_by = tuple(order_by)
        self._skip = skip
        self._limit = limit

    def __iter__(self):
        for node, in self.graph.run(*self._query_and_parameters):
            yield node

    def first(self):
        """ Evaluate the selection and return the first
        :py:class:`.Node` selected or :py:const:`None` if no matching
        nodes are found.

        :return: a single matching :py:class:`.Node` or :py:const:`None`
        """
        return self.graph.evaluate(*self._query_and_parameters)

    @property
    def _query_and_parameters(self):
        """ A tuple of the Cypher query and parameters used to select
        the nodes that match the criteria for this selection.

        :return: Cypher query string
        """
        clauses = ["MATCH (_%s)" % "".join(":%s" % cypher_escape(label) for label in self._labels)]
        parameters = {}
        if self._conditions:
            conditions = []
            for condition in self._conditions:
                if isinstance(condition, tuple):
                    condition, param = condition
                    parameters.update(param)
                conditions.append(condition)
            clauses.append("WHERE %s" % " AND ".join(conditions))
        clauses.append("RETURN _")
        if self._order_by:
            clauses.append("ORDER BY %s" % (", ".join(self._order_by)))
        if self._skip:
            clauses.append("SKIP %d" % self._skip)
        if self._limit is not None:
            clauses.append("LIMIT %d" % self._limit)
        return " ".join(clauses), parameters

    def where(self, *conditions, **properties):
        """ Create a new selection based on this selection. The
        criteria specified for refining the selection consist of
        conditions and properties. Conditions are individual Cypher
        expressions that would be found in a `WHERE` clause; properties
        are used as exact matches for property values.

        To refer to the current node within a condition expression, use
        the underscore character ``_``. For example::

            selection.where("_.name =~ 'J.*")

        Simple property equalities can also be specified::

            selection.where(born=1976)

        :param conditions: Cypher expressions to add to the selection
                           `WHERE` clause
        :param properties: exact property match keys and values
        :return: refined selection object
        """
        return self.__class__(self.graph, self._labels,
                              self._conditions + conditions + tuple(_property_equality_conditions(properties)),
                              self._order_by, self._skip, self._limit)

    def order_by(self, *fields):
        """ Order by the fields or field expressions specified.

        To refer to the current node within a field or field expression,
        use the underscore character ``_``. For example::

            selection.order_by("_.name", "max(_.a, _.b)")

        :param fields: fields or field expressions to order by
        :return: refined selection object
        """
        return self.__class__(self.graph, self._labels, self._conditions,
                              fields, self._skip, self._limit)

    def skip(self, amount):
        """ Skip the first `amount` nodes in the result.

        :param amount: number of nodes to skip
        :return: refined selection object
        """
        return self.__class__(self.graph, self._labels, self._conditions,
                              self._order_by, amount, self._limit)

    def limit(self, amount):
        """ Limit the selection to at most `amount` nodes.

        :param amount: maximum number of nodes to select
        :return: refined selection object
        """
        return self.__class__(self.graph, self._labels, self._conditions,
                              self._order_by, self._skip, amount)

    def paginate(self, page=None, per_page=None, error_out=True, max_per_page=None, count=True):
        """Returns ``per_page`` items from page ``page``.
        If ``page`` or ``per_page`` are ``None``, they will be retrieved from
        the request query. If ``max_per_page`` is specified, ``per_page`` will
        be limited to that value. If there is no request or they aren't in the
        query, they default to 1 and 20 respectively. If ``count`` is ``False``,
        no query to help determine total page count will be run.
        When ``error_out`` is ``True`` (default), the following rules will
        cause a 404 response:
        * No items are found and ``page`` is not 1.
        * ``page`` is less than 1, or ``per_page`` is negative.
        * ``page`` or ``per_page`` are not ints.
        When ``error_out`` is ``False``, ``page`` and ``per_page`` default to
        1 and 20 respectively.
        Returns a :class:`Pagination` object.
        """
        if request:
            if page is None:
                try:
                    page = int(request.args.get('page', 1))
                except (TypeError, ValueError):
                    if error_out:
                        abort(404)
                    page = 1
            if per_page is None:
                try:
                    per_page = int(request.args.get('per_page', 20))
                except (TypeError, ValueError):
                    if error_out:
                        abort(404)

                    per_page = 20
        else:
            if page is None:
                page = 1

            if per_page is None:
                per_page = 20

        if max_per_page is not None:
            per_page = min(per_page, max_per_page)

        if page < 1:
            if error_out:
                abort(404)
            else:
                page = 1

        if per_page < 0:
            if error_out:
                abort(404)
            else:
                per_page = 20

        items = list(self.__class__(
            self.graph,
            self._labels,
            self._conditions,
            self._order_by,
            (page - 1) * per_page,
            per_page
        ))

        if not items and page != 1 and error_out:
            abort(404)

        # No need to count if we're on the first page and there are fewer
        # items than we expected or if count is disabled.
        if not count:
            total = None
        elif page == 1 and len(items) < per_page:
            total = len(items)
        else:
            total = len(list(self.__class__(
                self.graph,
                self._labels,
                self._conditions,
                self._order_by,
                self._skip,
                self._limit
            )))

        return Pagination(self, page, per_page, total, items)


class NodeSelector(object):
    """ A :py:class:`.NodeSelector` can be used to locate nodes that
    fulfil a specific set of criteria. Typically, a single node can be
    identified passing a specific label and property key-value pair.
    However, any number of labels and any condition supported by the
    Cypher `WHERE` clause is allowed.

    For a simple selection by label and property::

        >>> from py2neo import Graph, NodeSelector
        >>> graph = Graph()
        >>> selector = NodeSelector(graph)
        >>> selected = selector.select("Person", name="Keanu Reeves")
        >>> list(selected)
        [(f9726ea:Person {born:1964,name:"Keanu Reeves"})]

    For a more comprehensive selection using Cypher expressions, the
    :meth:`.NodeSelection.where` method can be used for further
    refinement. Here, the underscore character can be used to refer to
    the node being filtered::

        >>> selected = selector.select("Person").where("_.name =~ 'J.*'", "1960 <= _.born < 1970")
        >>> list(selected)
        [(a03f6eb:Person {born:1967,name:"James Marshall"}),
         (e59993d:Person {born:1966,name:"John Cusack"}),
         (c44901e:Person {born:1960,name:"John Goodman"}),
         (b141775:Person {born:1965,name:"John C. Reilly"}),
         (e40244b:Person {born:1967,name:"Julia Roberts"})]

    The underlying query is only evaluated when the selection undergoes
    iteration or when a specific evaluation method is called (such as
    :meth:`.NodeSelection.first`). This means that a :class:`.NodeSelection`
    instance may be reused before and after a data changes for different
    results.
    """

    _selection_class = NodeSelection

    def __init__(self, graph):
        self.graph = graph
        self._all = self._selection_class(self.graph)

    def select(self, *labels, **properties):
        """ Describe a basic node selection using labels and property equality.

        :param labels: node labels to match
        :param properties: set of property keys and values to match
        :return: :py:class:`.NodeSelection` instance
        """
        if labels or properties:
            return self._selection_class(self.graph, frozenset(labels),
                                         tuple(_property_equality_conditions(properties)))
        else:
            return self._all


class Pagination(object):
    """Internal helper class returned by :meth:`BaseQuery.paginate`.  You
    can also construct it from any other SQLAlchemy query object if you are
    working with other libraries.  Additionally it is possible to pass `None`
    as query object in which case the :meth:`prev` and :meth:`next` will
    no longer work.
    """

    def __init__(self, query, page, per_page, total, items):
        #: the unlimited query object that was used to create this
        #: pagination object.
        self.query = query
        #: the current page number (1 indexed)
        self.page = page
        #: the number of items to be displayed on a page.
        self.per_page = per_page
        #: the total number of items matching the query
        self.total = total
        #: the items for the current page
        self.items = items

    @property
    def pages(self):
        """The total number of pages"""
        if self.per_page == 0 or self.total is None:
            pages = 0
        else:
            pages = int(ceil(self.total / float(self.per_page)))
        return pages

    def prev(self, error_out=False):
        """Returns a :class:`Pagination` object for the previous page."""
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return self.query.paginate(self.page - 1, self.per_page, error_out)

    @property
    def prev_num(self):
        """Number of the previous page."""
        if not self.has_prev:
            return None
        return self.page - 1

    @property
    def has_prev(self):
        """True if a previous page exists"""
        return self.page > 1

    def next(self, error_out=False):
        """Returns a :class:`Pagination` object for the next page."""
        assert self.query is not None, 'a query object is required ' \
                                       'for this method to work'
        return self.query.paginate(self.page + 1, self.per_page, error_out)

    @property
    def has_next(self):
        """True if a next page exists."""
        return self.page < self.pages

    @property
    def next_num(self):
        """Number of the next page"""
        if not self.has_next:
            return None
        return self.page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        """Iterates over the page numbers in the pagination.  The four
        parameters control the thresholds how many numbers should be produced
        from the sides.  Skipped page numbers are represented as `None`.
        This is how you could render such a pagination in the templates:
        .. sourcecode:: html+jinja
            {% macro render_pagination(pagination, endpoint) %}
              <div class=pagination>
              {%- for page in pagination.iter_pages() %}
                {% if page %}
                  {% if page != pagination.page %}
                    <a href="{{ url_for(endpoint, page=page) }}">{{ page }}</a>
                  {% else %}
                    <strong>{{ page }}</strong>
                  {% endif %}
                {% else %}
                  <span class=ellipsis>…</span>
                {% endif %}
              {%- endfor %}
              </div>
            {% endmacro %}
        """
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
                    (num > self.page - left_current - 1 and num < self.page + right_current) or \
                    num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

