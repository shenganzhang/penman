# -*- coding: utf-8 -*-

"""
Semantic models for interpreting graphs.
"""

from typing import cast, Tuple, List, Dict, Iterable, Mapping, Any
import re
from collections import defaultdict

from penman.exceptions import ModelError
from penman.types import (
    Identifier,
    Role,
    Constant,
    BasicTriple
)


_Reification = Tuple[Role, Constant, Role, Role]
_Reified = Tuple[Constant, Role, Role]


class Model(object):
    """
    A semantic model for Penman graphs.

    The model defines things like valid roles and transformations.

    Args:
        top_identifier: the identifier of the graph's top
        top_role: the role linking the graph's top to the top node
        nodetype_role: the role associated with node labels
        roles: a mapping of roles to associated data
        normalizations: a mapping of roles to normalized roles
        reifications: a list of 4-tuples used to define reifications
    """
    def __init__(self,
                 top_identifier: Identifier = 'top',
                 top_role: Role = ':TOP',
                 nodetype_role: Role = ':instance',
                 roles: Mapping[Role, Any] = None,
                 normalizations: Mapping[Role, Role] = None,
                 reifications: Iterable[_Reification] = None):
        self.top_identifier = top_identifier
        self.top_role = top_role
        self.nodetype_role = nodetype_role

        if roles:
            roles = dict(roles)
        self.roles = roles or {}
        self._role_re = re.compile(
            '^({})$'.format(
                '|'.join(list(self.roles) + [top_role, nodetype_role])))

        if normalizations:
            normalizations = dict(normalizations)
        self.normalizations = normalizations or {}

        reifs: Dict[Role, List[_Reified]] = defaultdict(list)
        if reifications:
            for role, label, source, target in reifications:
                reifs[role].append((label, source, target))
        self.reifications = dict(reifs)

    def __eq__(self, other):
        if not isinstance(other, Model):
            return NotImplemented
        return (self.top_identifier == other.top_identifier
                and self.top_role == other.top_role
                and self.nodetype_role == other.nodetype_role
                and self.roles == other.roles
                and self.normalizations == other.normalizations
                and self.reifications == other.reifications)

    @classmethod
    def from_dict(cls, d):
        """Instantiate a model from a dictionary."""
        return cls(**d)

    def has_role(self, role: Role) -> bool:
        """
        Return `True` if *role* is defined by the model.

        If *role* is not in the model but a single deinversion of
        *role* is in the model, then `True` is returned. Otherwise
        `False` is returned, even if something like
        :meth:`canonicalize_role` could return a valid role.
        """
        return (self._has_role(role)
                or (role.endswith('-of') and self._has_role(role[:-3])))

    def _has_role(self, role: Role) -> bool:
        return self._role_re.match(role) is not None

    def is_role_inverted(self, role: Role) -> bool:
        """Return `True` if *role* is inverted."""
        return not self._has_role(role) and role.endswith('-of')

    def invert_role(self, role: Role) -> Role:
        """Invert *role*."""
        if not self._has_role(role) and role.endswith('-of'):
            inverse = role[:-3]
        else:
            inverse = role + '-of'
        return inverse

    def invert(self, triple: BasicTriple) -> BasicTriple:
        """
        Invert *triple*.

        This will invert or deinvert a triple regardless of its
        current state. :meth:`deinvert` will deinvert a triple only if
        it is already inverted. Unlike :meth:`canonicalize`, this will
        not perform multiple inversions or replace the role with a
        normalized form.
        """
        source, role, target = triple
        inverse = self.invert_role(role)
        # casting is just for the benefit of the type checker; it does
        # not actually check that target is a valid identifier type
        target = cast(Identifier, target)
        return (target, inverse, source)

    def deinvert(self, triple: BasicTriple) -> BasicTriple:
        """
        De-invert *triple* if it is inverted.

        Unlike :meth:`invert`, this only inverts a triple if the model
        considers it to be already inverted, otherwise it is left
        alone. Unlike :meth:`canonicalize`, this will not normalize
        multiple inversions or replace the role with a normalized
        form.
        """
        if self.is_role_inverted(triple[1]):
            triple = self.invert(triple)
        return triple

    def canonicalize_role(self, role: Role) -> Role:
        """
        Canonicalize *role*.

        Role canonicalization will do the following:

        * Ensure the role starts with `':'`

        * Normalize multiple inversions (e.g., `ARG0-of-of` becomes
          `ARG0`), but it does *not* change the direction of the role

        * Replace the resulting role with a normalized form if one is
          defined in the model
        """
        if not role.startswith(':'):
            role = ':' + role
        role = self._canonicalize_inversion(role)
        role = self.normalizations.get(role, role)
        return role

    def _canonicalize_inversion(self, role: Role) -> Role:
        invert = self.invert_role
        if not self._has_role(role):
            while True:
                prev = role
                inverse = invert(role)
                role = invert(inverse)
                if prev == role:
                    break
        return role

    def canonicalize(self, triple: BasicTriple) -> BasicTriple:
        """
        Canonicalize *triple*.

        See :meth:`canonicalize_role` for a description of how the
        role is canonicalized. Unlike :meth:`invert`, this does not
        swap the source and target of *triple*.
        """
        source, role, target = triple
        canonical = self.canonicalize_role(role)
        return (source, canonical, target)

    def is_reifiable(self, triple: BasicTriple) -> bool:
        """Return `True` if the role of *triple* can be reified."""
        return triple[1] in self.reifications

    def reify(self, triple: BasicTriple) -> List[BasicTriple]:
        """
        Return the list of triples that reify *triple*.

        Note that the node identifier for the reified node is not
        necessarily valid for the target graph. When incorporating
        the reified triples, this identifier should be replaced.

        If the role of *triple* does not have a defined reification, a
        :exc:`ModelError` is raised.
        """
        source, role, target = triple
        if role not in self.reifications:
            raise ModelError("'{}' cannot be reified".format(role))
        label, source_role, target_role = next(iter(self.reifications[role]))
        dummy_id = '_'
        return [(source, self.invert_role(source_role), dummy_id),
                (dummy_id, self.nodetype_role, label),
                (dummy_id, target_role, target)]
