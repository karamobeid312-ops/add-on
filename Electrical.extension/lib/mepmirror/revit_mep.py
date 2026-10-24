# -*- coding: utf-8 -*-
"""Revit side of Mirror Tower (Mechanical / Plumbing).

The tool's elements are read once (read_model), each as a plan.Thing on
its floor and its side (rules: mechanical or plumbing). On each chosen
floor, the Tower 1 elements Tower 2 has not got yet are mirrored in ONE
Revit Mirror (ElementTransformUtils.MirrorElements, copies), so the
copies keep their connections to each other, and moved into Tower 2,
like the electrical Mirror Tower. Elements on a wall are placed again on
Tower 2's wall (mirrortower.revit_mirror._rehost): a move off a wall's
plane is dropped by Revit. Then the open ends of the copies are joined to
any open end at the same spot (Tower 2's own pipes, a re-placed fixture).

No parameter is created: the copies keep Tower 1's values as Revit's
Mirror does, and re-placed ones get them copied over.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import time

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ConnectorType, Domain, ElementId,
    ElementTransformUtils, FamilyInstance, FilteredElementCollector, IndependentTag,
    LeaderEndCondition, LocationCurve, LocationPoint, Reference, XYZ,
)
from System.Collections.Generic import List

from copycircuits import revit_copy as rc
from mepmirror import plan, rules
from mirrortower import revit_mirror

id_int = rc.id_int
_INVALID = id_int(ElementId.InvalidElementId)


def _bic(name):
    return getattr(BuiltInCategory, name, None)


def categories(domain, unticked=()):
    """{category id (int): BuiltInCategory name} the tool takes, but the
    ones unticked in Setup."""
    found = {}
    for name, _ in rules.CATEGORIES[domain]:
        bic = _bic(name)
        if bic is not None and name not in unticked:
            found[int(bic)] = name
    return found


def _category(element):
    try:
        return id_int(element.Category.Id)
    except Exception:
        return None


def _get(doc, key):
    return revit_mirror._get(doc, key)


# ---------------------------------------------------------------- reading

def connectors(element):
    manager = None
    try:
        manager = element.ConnectorManager           # ducts, pipes, flexes
    except Exception:
        pass
    if manager is None:
        try:
            manager = element.MEPModel.ConnectorManager
        except Exception:
            manager = None
    if manager is None:
        return []
    try:
        return list(manager.Connectors)
    except Exception:
        return []


def _text(element, name):
    bip = getattr(BuiltInParameter, name, None)
    if bip is None:
        return u""
    try:
        p = element.get_Parameter(bip)
        if p is None:
            return u""
        return p.AsString() or p.AsValueString() or u""
    except Exception:
        return u""


def _pipe_domain(element):
    names = [_text(element, n) for n in ("RBS_SYSTEM_NAME_PARAM", "RBS_PIPING_SYSTEM_TYPE_PARAM",
                                         "RBS_SYSTEM_ABBREVIATION_PARAM")]
    return rules.pipe_domain(_text(element, "RBS_SYSTEM_CLASSIFICATION_PARAM"), names)


def _equipment_domain(element):
    ducts, pipes = 0, []
    for c in connectors(element):
        try:
            if c.Domain == Domain.DomainHvac:
                ducts += 1
            elif c.Domain == Domain.DomainPiping:
                names = []
                try:
                    if c.MEPSystem is not None:
                        names.append(c.MEPSystem.Name)
                except Exception:
                    pass
                pipes.append(rules.pipe_domain(u"%s" % c.PipeSystemType, names))
        except Exception:
            pass
    return rules.equipment_domain(ducts, pipes, _label(element, None))


def _fixture_domain(element):
    pipes = []
    for c in connectors(element):
        try:
            if c.Domain == Domain.DomainPiping:
                names = []
                try:
                    if c.MEPSystem is not None:
                        names.append(c.MEPSystem.Name)
                except Exception:
                    pass
                pipes.append(rules.pipe_domain(u"%s" % c.PipeSystemType, names))
        except Exception:
            pass
    return rules.fixture_domain(pipes, _label(element, None))


def _neighbours(element):
    found = []
    for c in connectors(element):
        try:
            for other in c.AllRefs:
                owner = other.Owner
                if owner is not None and id_int(owner.Id) != id_int(element.Id):
                    found.append(id_int(owner.Id))
        except Exception:
            pass
    return found


def _label(element, category):
    try:
        return u"%s : %s" % (element.Symbol.Family.Name, element.Name)
    except Exception:
        pass
    name = rules.LABELS.get(category)
    if name is None:
        try:
            name = element.Category.Name
        except Exception:
            name = u""
    try:
        kind = element.Document.GetElement(element.GetTypeId())
        return u"%s : %s" % (name, kind.Name if kind else u"")
    except Exception:
        return name or u"(unknown)"


def thing(element, category=None):
    """plan.Thing of a duct, pipe or family instance, or None."""
    location = element.Location
    a = b = None
    if isinstance(location, LocationCurve):
        try:
            curve = location.Curve
            p, q = curve.GetEndPoint(0), curve.GetEndPoint(1)
            a, b = (p.X, p.Y, p.Z), (q.X, q.Y, q.Z)
        except Exception:
            return None
    elif isinstance(location, LocationPoint):
        p = location.Point
        a = (p.X, p.Y, p.Z)
    else:
        return None
    try:
        grouped = id_int(element.GroupId) != _INVALID
    except Exception:
        grouped = False
    return plan.Thing(id_int(element.Id), rc._type_key(element), a, b, rc._family_key(element),
                      rc.level_key(element), _label(element, category), grouped)


class Model(object):
    """The tool's elements, read once: by floor, with the floors' heights."""

    def __init__(self):
        self.floors = []            # [(level key, low, high)] all levels
        self.names = {}             # level key -> name
        self.levels = {}            # level key -> Level
        self.things = {}            # level key -> [Thing]
        self.elements = {}          # key -> element
        self.categories = {}        # key -> BuiltInCategory name
        self.other_side = {}        # other tool's side -> its elements here (pipes...)
        self.domain = None
        self.links = True           # walls of the links read for wall fixtures
        self.cat_names = {}         # category id -> BuiltInCategory name


def read_model(doc, domain, unticked=()):
    cats = categories(domain, unticked)
    model = Model()
    model.domain = domain
    model.links = domain != rules.MECHANICAL       # the user's rule: Mechanical reads no link
    model.cat_names = cats
    all_levels = rc.levels(doc)
    for level in all_levels:
        f = rc.Floor(level, all_levels)
        model.floors.append((f.key, f.low, f.high))
        model.names[f.key] = level.Name
        model.levels[f.key] = level
    pending, sides, neighbours = {}, {}, {}
    for cat_id, name in cats.items():
        for e in FilteredElementCollector(doc).OfCategory(_bic(name)) \
                .WhereElementIsNotElementType():
            try:
                if isinstance(e, FamilyInstance) and e.SuperComponent is not None:
                    continue            # nested: goes with its parent
            except Exception:
                pass
            t = thing(e, name)
            if t is None:
                continue
            pending[t.key] = (t, e, name)
            if name in rules.PIPED:
                sides[t.key] = _pipe_domain(e)
            elif name in rules.EQUIPMENT:
                sides[t.key] = _equipment_domain(e)
            elif name in rules.FIXTURES:
                sides[t.key] = _fixture_domain(e)
            else:
                sides[t.key] = rules.FIXED.get(name, domain)
    for key, side in sides.items():
        if side is None:
            neighbours[key] = _neighbours(pending[key][1])
    sides = rules.settle(sides, neighbours)
    for key, (t, e, name) in pending.items():
        if sides[key] != domain:
            model.other_side[sides[key]] = model.other_side.get(sides[key], 0) + 1
            continue
        floor = plan.pick_floor(t, model.floors)
        if floor is None:
            continue
        model.things.setdefault(floor, []).append(t)
        model.elements[key] = e
        model.categories[key] = name
    return model


def add_new(doc, model, results):
    """The copies just made added to the model, so the floors show them
    without reading the whole model again."""
    for r in results:
        for i in r.mirrored:
            e = doc.GetElement(i)
            name = model.cat_names.get(_category(e)) if e is not None else None
            if name is None:
                continue
            t = thing(e, name)
            floor = plan.pick_floor(t, model.floors) if t is not None else None
            if floor is None:
                continue
            model.things.setdefault(floor, []).append(t)
            model.elements[t.key] = e
            model.categories[t.key] = name


def in_links(doc, domain, unticked=()):
    """[(linked model title, count)] of the tool's categories in the loaded
    links: a tool can only change the model that is open, so when this
    model has none, they are likely in the MEP model linked here."""
    found, seen = [], set()
    for _, link_doc in revit_mirror.linked_models(doc):
        title = link_doc.Title
        if title in seen:
            continue
        seen.add(title)
        n = 0
        for name in categories(domain, unticked).values():
            try:
                n += FilteredElementCollector(link_doc).OfCategory(_bic(name)) \
                    .WhereElementIsNotElementType().GetElementCount()
            except Exception:
                pass
        if n:
            found.append((title, n))
    found.sort(key=lambda p: -p[1])
    return found


# ---------------------------------------------------------------- tags

def _tagged_keys(tag):
    try:
        return [id_int(i) for i in tag.GetTaggedLocalElementIds()]      # Revit 2022+
    except Exception:
        pass
    try:
        return [id_int(tag.TaggedLocalElementId)]
    except Exception:
        return []


class Tags(object):
    """The model's tags (IndependentTag) by the element they tag, read once
    per run."""

    def __init__(self, doc):
        self.by_element = {}
        for tag in FilteredElementCollector(doc).OfClass(IndependentTag):
            for k in _tagged_keys(tag):
                self.by_element.setdefault(k, []).append(tag)

    def has(self, key, view_key, type_key):
        return any(id_int(t.OwnerViewId) == view_key and id_int(t.GetTypeId()) == type_key
                   for t in self.by_element.get(key, ()))

    def add(self, key, tag):
        self.by_element.setdefault(key, []).append(tag)


def _moved_point(placement, p):
    x, y = placement.apply(p.X, p.Y)
    return XYZ(x, y, p.Z)


def _reference_of(tag):
    try:
        refs = tag.GetTaggedReferences()                                  # Revit 2022+
        return refs[0] if refs.Count else None
    except Exception:
        return None


def _leader(tag, new_tag, new_ref, placement, head):
    """Tower 1 tag's leader mirrored onto the new tag: its end condition,
    its free end and its elbow. A leader with no elbow stays straight:
    Revit gives a new leader an elbow of its own, so the copy's elbow is
    put on the straight line from its end to its head."""
    try:
        new_tag.LeaderEndCondition = tag.LeaderEndCondition
    except Exception:
        pass
    ref = _reference_of(tag)
    end = None
    try:
        if tag.LeaderEndCondition == LeaderEndCondition.Free:
            if ref is not None:
                end = _moved_point(placement, tag.GetLeaderEnd(ref))
                new_tag.SetLeaderEnd(new_ref, end)
            else:
                end = _moved_point(placement, tag.LeaderEnd)
                new_tag.LeaderEnd = end
    except Exception:
        end = None
    try:
        if ref is not None:
            has, set_elbow = tag.HasLeaderElbow(ref), \
                lambda p: new_tag.SetLeaderElbow(new_ref, p)
            elbow = tag.GetLeaderElbow(ref) if has else None
        else:
            has = tag.HasElbow
            elbow = tag.LeaderElbow if has else None

            def set_elbow(p):
                new_tag.LeaderElbow = p
        if has:
            set_elbow(_moved_point(placement, elbow))
        elif end is not None:
            set_elbow(XYZ(end.X + (head.X - end.X) * 0.25, end.Y + (head.Y - end.Y) * 0.25,
                          end.Z + (head.Z - end.Z) * 0.25))
    except Exception:
        pass


def mirror_tags(doc, tags, pairs, placement):
    """Tower 1's tags made again on Tower 2's copies, in the same views, at
    the mirrored spot (text is never mirrored). pairs: [(Tower 1 key, Tower
    2 element)]. A copy that has a tag of that type in that view already is
    left as it is. Returns how many tags were made."""
    made = 0
    for key, element in pairs:
        if element is None:
            continue
        target = id_int(element.Id)
        try:        # a wire is in one view: its tag goes there
            view_id = element.OwnerViewId if element.ViewSpecific else None
        except Exception:
            view_id = None
        for tag in list(tags.by_element.get(key, ())):
            try:
                view = view_id if view_id is not None else tag.OwnerViewId
                view_key, type_key = id_int(view), id_int(tag.GetTypeId())
                if tags.has(target, view_key, type_key):
                    continue
                ref = Reference(element)
                head = _moved_point(placement, tag.TagHeadPosition)
                new_tag = IndependentTag.Create(doc, tag.GetTypeId(), view, ref,
                                                tag.HasLeader, tag.TagOrientation, head)
                new_tag.TagHeadPosition = head
                if tag.HasLeader:
                    _leader(tag, new_tag, ref, placement, head)
                tags.add(target, new_tag)
                made += 1
            except Exception:
                pass
    return made


# ---------------------------------------------------------------- mirroring

class FloorResult(object):
    """What happened on one floor."""

    def __init__(self, name):
        self.floor = name
        self.tower1 = 0             # Tower 1 elements
        self.already = 0            # of them, in Tower 2 already
        self.shared = 0             # on the mirror line, not mirrored
        self.leaves = []            # ids of runs leaving Tower 1: skipped
        self.grouped = []           # ids of Tower 1 elements in groups: skipped
        self.mirrored = []          # new element ids
        self.rehosted = 0           # of them, placed again on Tower 2's walls
        self.off_spot = []          # new ids Revit kept off their Tower 2 spot
        self.joined = 0             # open ends joined
        self.tags = 0               # tags made on Tower 2's copies
        self.no_wall = []           # Tower 1 ids with no wall at their Tower 2 spot
        self.refused = []           # Tower 1 ids Revit did not mirror
        self.errors = []            # what Revit said
        self.why = {}               # (family : type, why not placed) -> count
        self.made = {}              # Tower 1 key -> its new copy's ElementId
        # electrical only (mepmirror.electrical)
        self.renamed = []           # (Tower 1 board name, Tower 2 board name)
        self.not_renamed = []       # board names to check by hand
        self.by_name = []           # (Tower 1 board, Tower 2 board found by name)
        self.circuits = None        # copycircuits LevelResult: circuits and wires made
        self.seconds = {}           # step -> seconds it took


def _id_list(ids):
    found = List[ElementId]()
    for i in ids:
        found.Add(i)
    return found


def _mirror(doc, elements, plane, result, tags_of=None):
    """Mirror copies of the elements, all at once (they stay connected),
    with their tags (tags_of: {element key: [tag ids]}) in the same Mirror,
    so the copies are tagged with Tower 1's leaders exactly. When Revit
    refuses the lot, it is mirrored in halves (see _halves). Returns the
    new ElementIds."""
    tags_of = tags_of or {}
    groups = [(e, list(tags_of.get(id_int(e.Id), ()))) for e in elements]
    return _halves(doc, groups, plane, result)


def _try_mirror(doc, ids, plane):
    """The new ids, or the error (None when Revit cannot mirror them)."""
    try:
        ids = _id_list(ids)
        if ElementTransformUtils.CanMirrorElements(doc, ids):
            made = ElementTransformUtils.MirrorElements(doc, ids, plane, True)
            if made is not None:
                return list(made)
    except Exception as error:
        return error
    return None


def _halves(doc, groups, plane, result):
    """Mirror the (element, its tag ids) groups as one lot; when Revit
    refuses it, in halves, and the halves of a half refused again, down to
    the single elements (tried without their tags last) Revit will not
    mirror. A few bad elements cost a few dozen Mirrors, not one each."""
    got = _try_mirror(doc, [i for e, tags in groups for i in [e.Id] + tags], plane)
    if isinstance(got, list):
        return got
    if len(groups) == 1:
        e, tags = groups[0]
        if tags:
            got = _try_mirror(doc, [e.Id], plane)
            if isinstance(got, list):
                return got
        result.refused.append(e.Id)
        if got is not None:
            text = rc._message(got)
            if text not in result.errors:
                result.errors.append(text)
        return []
    middle = len(groups) // 2
    return _halves(doc, groups[:middle], plane, result) + \
        _halves(doc, groups[middle:], plane, result)


def _walls(doc, things, placement, floor, links=True):
    spots = [placement.apply(t.a[0], t.a[1]) for t in things]
    pad = 5.0
    extent = (min(x for x, _ in spots) - pad, min(y for _, y in spots) - pad,
              max(x for x, _ in spots) + pad, max(y for _, y in spots) + pad)
    _, low, high = floor
    return revit_mirror.WallIndex(doc, extent, low, high if high is not None else low + 30.0,
                                  links)


def _open_ends(doc, keys):
    """[(owner key, connector id, (x, y, z), domain)] of the elements' free
    duct and pipe ends."""
    ends = []
    for key in keys:
        e = _get(doc, key)
        if e is None:
            continue
        for c in connectors(e):
            try:
                if c.ConnectorType != ConnectorType.End or c.IsConnected:
                    continue
                if c.Domain not in (Domain.DomainHvac, Domain.DomainPiping):
                    continue
                o = c.Origin
                ends.append((key, c.Id, (o.X, o.Y, o.Z), u"%s" % c.Domain))
            except Exception:
                pass
    return ends


def _connector(doc, key, connector_id):
    e = _get(doc, key)
    for c in connectors(e) if e is not None else []:
        try:
            if c.Id == connector_id:
                return c
        except Exception:
            pass
    return None


REACH = 3.0         # ft: an element with an end this near a new open end may meet it


def join_open_ends(doc, new_keys, around):
    """Connect each free end of the new elements to a free end at the same
    spot (of another new one or one of the `around` Things near them).
    Returns how many."""
    new_keys = set(new_keys)
    ends = _open_ends(doc, list(new_keys))
    if not ends:
        return 0
    others = plan.near([t for t in around if t.key not in new_keys], [e[2] for e in ends],
                       REACH)
    ends += _open_ends(doc, list(others))
    joined = 0
    for e, f in plan.joints(ends):
        if e[0] not in new_keys and f[0] not in new_keys:
            continue
        a, b = _connector(doc, e[0], e[1]), _connector(doc, f[0], f[1])
        if a is None or b is None:
            continue
        try:
            a.ConnectTo(b)
            joined += 1
        except Exception:
            pass
    return joined


def _on_a_face(element):
    """A hosted family facing sideways: on a wall Revit's move could not
    carry it off (equipment standing free is never re-placed)."""
    try:
        hosted = element.Host is not None or element.HostFace is not None
    except Exception:
        hosted = False
    facing = revit_mirror._facing_out(element)
    return hosted and facing is not None and abs(facing[2]) < 0.3


class _Clock(object):
    """Times each part of a floor's run (result.seconds) and tells the
    window how far it is: report(share of the floor done, text)."""

    def __init__(self, result, report):
        self.result = result
        self.report = report
        self.name = None
        self.start = time.time()

    def step(self, name, share, text=None):
        self.stop()
        self.name, self.start = name, time.time()
        if self.report is not None:
            self.report(share, text or name)

    def stop(self):
        if self.name is not None:
            seconds = self.result.seconds
            seconds[self.name] = seconds.get(self.name, 0.0) + time.time() - self.start
        self.name = None


def mirror_floor(doc, model, floor, side, placement, about, tolerance, join=True, tags=None,
                 report=None):
    """Mirror the floor's missing Tower 1 elements into Tower 2. floor:
    (level key, low, high). report(share, text): how far it is. Returns a
    FloorResult."""
    key, _, _ = floor
    result = FloorResult(model.names.get(key, u""))
    clock = _Clock(result, report)
    result.tower1 = len(side.tower1)
    result.already = len(side.copies)
    result.shared = len(side.shared)
    result.leaves = [model.elements[t.key].Id for t in side.leaves]
    result.grouped = [model.elements[t.key].Id for t in side.grouped]
    if not side.missing:
        if tags is not None and side.copies:
            tx = revit_mirror._transaction(doc, "Mirror Tower tags: %s" % result.floor)
            tx.Start()
            try:
                result.tags = mirror_tags(doc, tags, [(k, _get(doc, t)) for k, t in
                                                      side.copies.items()], placement)
                tx.Commit()
            except Exception:
                if tx.HasStarted() and not tx.HasEnded():
                    tx.RollBack()
                raise
        return result
    level = model.levels.get(key)
    elements = dict((t.key, model.elements[t.key]) for t in side.missing)
    walled = [t for t in side.missing if not t.run and revit_mirror.on_wall(elements[t.key])]
    walled_keys = set(t.key for t in walled)
    rest = [t for t in side.missing if t.key not in walled_keys]
    # rough share of the floor's time: a wall item placed again costs about 3 mirrored ones
    work = 3.0 * len(walled) + len(rest) + 10.0
    wall_share = 3.0 * len(walled) / work
    del revit_mirror._ERRORS[:]
    tx = revit_mirror._transaction(doc, "Mirror Tower: %s" % result.floor)
    tx.Start()
    try:
        walls, made = None, {}          # Tower 1 key -> new element
        if walled:
            clock.step(u"reading walls", 0.0, u"%s: reading Tower 2's walls..." % result.floor)
            walls = _walls(doc, walled, placement, floor, model.links)
            clock.step(u"placing on walls", 0.02, u"%s: placing %d items on Tower 2's walls..."
                       % (result.floor, len(walled)))

            def tick(i, n):
                if report is not None and (i % 10 == 0 or i == n):
                    report(0.02 + wall_share * i / max(n, 1),
                           u"%s: placing on Tower 2's walls %d / %d..." % (result.floor, i, n))
            made.update(revit_mirror._rehost(doc, [t.key for t in walled], elements, placement,
                                             walls, level, result, tick))
            result.rehosted = len(made)
        if rest:
            clock.step(u"mirroring", 0.02 + wall_share, u"%s: mirroring %d elements..." % (
                result.floor, len(rest)))
            plane, move = revit_mirror._plane(placement, about)
            tags_of = {}
            if tags is not None:
                for t in rest:
                    tags_of[t.key] = [tag.Id for tag in tags.by_element.get(t.key, ())]
            new_ids = _mirror(doc, [elements[t.key] for t in rest], plane, result, tags_of)
            # the copies of the tool's categories (not the insulation that comes along)
            cats = set(int(_bic(n)) for n in set(model.categories.values()))
            ours = [e for e in (doc.GetElement(i) for i in new_ids)
                    if e is not None and _category(e) in cats]
            copied_tags = [e for e in (doc.GetElement(i) for i in new_ids)
                           if isinstance(e, IndependentTag)]
            new_keys = set(id_int(e.Id) for e in ours)
            for tag in list(copied_tags):
                if not set(_tagged_keys(tag)) & new_keys:   # still on Tower 1's element
                    doc.Delete(tag.Id)
                    copied_tags.remove(tag)
            moving = [e.Id for e in ours] + [tag.Id for tag in copied_tags]
            if moving and move.GetLength() > 1e-9:
                ElementTransformUtils.MoveElements(doc, _id_list(moving), move)
            for tag in copied_tags:
                for k in _tagged_keys(tag):
                    tags.add(k, tag)
            result.tags += len(copied_tags)
            doc.Regenerate()
            clock.step(u"checking copies", 0.02 + wall_share + 0.8 * (1 - wall_share) * 0.8,
                       u"%s: checking the copies landed in Tower 2..." % result.floor)
            things = {}
            for e in ours:
                if isinstance(e, FamilyInstance) and e.SuperComponent is not None:
                    continue
                t = thing(e)
                if t is None:
                    result.off_spot.append(e.Id)
                    continue
                things[t.key] = (t, e)
            found = plan.landed(rest, [t for t, _ in things.values()], placement, tolerance)
            back = dict((n, k) for k, n in found.items())
            for n, (t, e) in things.items():
                if n in back:
                    made[back[n]] = e
                elif not t.run and isinstance(e, FamilyInstance) and _on_a_face(e):
                    doc.Delete(e.Id)        # kept on Tower 1's wall plane: placed again
                else:
                    result.off_spot.append(e.Id)
            again = [t for t in rest if t.key not in found and _on_a_face(elements[t.key])
                     and not t.run]
            if again:
                clock.step(u"placing on walls", 0.85, u"%s: placing %d more on Tower 2's "
                           u"walls..." % (result.floor, len(again)))
                if walls is None:
                    walls = _walls(doc, again, placement, floor, model.links)
                placed = revit_mirror._rehost(doc, [t.key for t in again], elements, placement,
                                              walls, level, result)
                made.update(placed)
                result.rehosted += len(placed)
            doc.Regenerate()
        for k, e in made.items():
            rc.keep_workset(elements[k], e)     # the copy stays on Tower 1's workset
        if join and made:
            clock.step(u"joining ends", 0.88, u"%s: joining open ends..." % result.floor)
            result.joined = join_open_ends(doc, [id_int(e.Id) for e in made.values()],
                                           side.pool + side.shared)
        if tags is not None:
            clock.step(u"tags", 0.9, u"%s: tags..." % result.floor)
            pairs = [(k, e) for k, e in made.items()] + \
                [(k, _get(doc, t)) for k, t in side.copies.items()]
            result.tags += mirror_tags(doc, tags, pairs, placement)
        clock.step(u"saving the floor", 0.93, u"%s: Revit is saving the floor..." % result.floor)
        tx.Commit()
        clock.stop()
    except Exception:
        if tx.HasStarted() and not tx.HasEnded():
            tx.RollBack()
        raise
    for text in revit_mirror._ERRORS:
        if text not in result.errors:
            result.errors.append(text)
    refused = set(id_int(i) for i in result.refused) | set(id_int(i) for i in result.no_wall)
    for k, e in made.items():
        if e is None or not e.IsValidObject:
            if k not in refused:
                result.refused.append(elements[k].Id)
            continue
        result.mirrored.append(e.Id)
        result.made[k] = e.Id
    result.off_spot = [i for i in result.off_spot if doc.GetElement(i) is not None]
    return result
