from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from .db import DB
from .fields import Field, IntegerField
from .sql import build_insert, build_search

registry = {}


class RecordSet:
    def __init__(self, model_class: type, domain: list, records: list | None = None):
        self.model_class = model_class
        self.domain = domain
        # Si records est fourni (ex: après un filtrage), le cache est pré-rempli
        self._cache: list | None = records

    def filtered(self, predicate_lambda) -> RecordSet:
        """[MUST 5.5] Permet le chaînage après le search sans ré-exécuter le SQL brut."""
        # Évalue le RecordSet actuel pour obtenir les instances en mémoire
        records = self._evaluate()
        # Applique le filtre de l'utilisateur
        filtered_records = [r for r in records if predicate_lambda(r)]
        # Renvoie un NOUVEAU RecordSet avec le cache déjà peuplé
        return RecordSet(self.model_class, self.domain, records=filtered_records)

    def _evaluate(self) -> list:
        """Méthode interne qui effectue la requête SQL au tout dernier moment."""
        if self._cache is not None:
            return self._cache

        if self.model_class._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")

        # 1. On délègue la génération de la requête au module sql.py !
        query, params = build_search(self.model_class, self.domain)

        # 2. Exécution de la requête via votre connexion globale [MUST 5.2]
        cursor = self.model_class._db.execute(query, params)
        rows = cursor.fetchall()

        # 3. Extraction des colonnes pour instancier vos modèles
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        self._cache = []
        for row in rows:
            if isinstance(row, tuple):
                row_data = dict(zip(col_names, row, strict=True))
            else:
                row_data = row

            self._cache.append(self.model_class(**row_data))

        return self._cache

    # --- [MUST 5.5] Déclencheurs magiques d'évaluation tardive ---
    def __len__(self) -> int:
        return len(self._evaluate())

    def __bool__(self) -> bool:
        return bool(self._evaluate())

    def __iter__(self) -> Iterator:
        return iter(self._evaluate())

    def __repr__(self) -> str:
        # Pratique pour le debugging dans vos tests
        return f"<RecordSet {self.model_class.__name__} (cached={self._cache is not None})>"

    def __getitem__(self, index: int | slice) -> Any:
        """
        Permet d'accéder aux enregistrements avec des crochets (ex: records[0]).
        Déclenche l'évaluation de la requête SQL si ce n'est pas déjà fait.
        """
        return self._evaluate()[index]


class ModelMeta(type):
    def __new__(mcs, name: str, bases: tuple, attrs: dict[str, Any]):
        # 1. Collect fields from parent classes
        fields: dict[str, Field] = {}
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # 2. Add fields from current class
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, Field):
                attr_value.__set_name__(None, attr_name)
                fields[attr_name] = attr_value

        # 3. Auto-add id field if not present and not base Model
        if name != "Model" and "id" not in fields:
            id_field = IntegerField(required=True)
            id_field.__set_name__(None, "id")
            fields["id"] = id_field

        # 4. Store fields on the class
        attrs["_fields"] = fields

        # 5. Create the class
        cls = super().__new__(mcs, name, bases, attrs)

        # 6. Register in registry (except base class) - lowercase key
        if name != "Model":
            registry[name.lower()] = cls

        return cls


class Model(metaclass=ModelMeta):
    _fields: ClassVar[dict[str, Field]] = {}
    _db: ClassVar[DB | None] = None

    @classmethod
    def set_db(cls, db: DB) -> None:
        """Designate the shared connection wrapper; every model issues SQL through it."""
        Model._db = db

    def __init__(self, **kwargs):
        for field_name, field in self._fields.items():
            value = kwargs.get(field_name, getattr(field, "default", None))
            setattr(self, field_name, value)

    @classmethod
    def create(cls, values: dict):
        instance = cls(**values)
        instance.save()
        return instance

    def save(self):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")
        values = {name: getattr(self, name) for name in self._fields if name != "id"}
        if self.id is None:
            row = Model._db.execute(*build_insert(type(self), values)).fetchone()
            if row is None:
                raise RuntimeError(f"INSERT ... RETURNING id returned no row for {type(self).__name__}")
            self.id = row[0]
        else:
            raise NotImplementedError("UPDATE not implemented yet")

    @classmethod
    def search(cls, domain: list | None = None) -> RecordSet:
        """
        [MUST 5.5] Ne déclenche aucun SQL à l'appel.
        Renvoie l'objet RecordSet paresseux (lazy).
        """
        if domain is None:
            domain = []
        return RecordSet(model_class=cls, domain=domain)

    @classmethod
    def browse(cls, id):
        return cls()

    def write(self, values: dict):
        for key, value in values.items():
            setattr(self, key, value)

    def unlink(self):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")
        if self.id is not None:
            Model._db.execute(*build_delete(type(self), self.id))
            self.id = None
