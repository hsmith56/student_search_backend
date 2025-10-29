from typing import Tuple
from models.search_filters import SearchFilters
from models.student import FullStudent
from rapidfuzz import fuzz, utils


def filter_students(students: Tuple[FullStudent], filters: SearchFilters):
    res: Tuple[FullStudent] = tuple(students)

    if filters.statusOptions is not None and "All" not in filters.statusOptions:
        lower_options = [x.lower() for x in filters.statusOptions]
        res = tuple(
            s
            for s in res
            if any(opt in s.placement_status.lower() for opt in lower_options)
        )

    if filters.gender_female is not None and filters.gender_male is not None:
        if filters.gender_female is True and filters.gender_male is True:
            pass
        elif filters.gender_female is True:
            res = tuple(s for s in res if s.gender_desc.lower() == "female")
        elif filters.gender_male is True:
            res = tuple(s for s in res if s.gender_desc.lower() == "male")

        print(f"\t1. {len(res)}")

    if filters.state and filters.state != "all":
        res = tuple(
            s for s in res if filters.state.lower() in [st.lower() for st in s.states]
        )
        print(f"\t2. {len(res)}")

    if filters.interests:
        if filters.interests.lower() == "all":
            pass
        else:
            print(res[0].selected_interests)
            res = tuple(s for s in res if filters.interests in s.selected_interests)
            print(f"\t3. {len(res)}")

    if filters.gpa and filters.gpa != "all":
        try:
            gpa_value = float(filters.gpa)
            res = tuple(s for s in res if s.gpa and float(s.gpa) >= gpa_value)
        except ValueError:
            pass
        print(f"\t4. {len(res)}")

    if filters.pets_in_home is not None and isinstance(filters.pets_in_home, str):
        if filters.pets_in_home != "all":
            mapping = {"yes": True, "no": False}
            res = tuple(
                s for s in res if s.live_with_pets is mapping.get(filters.pets_in_home)
            )
            print(f"\t5. {len(res)}")

    if filters.usahsId:
        res = tuple(s for s in res if filters.usahsId.lower() in s.usahsid.lower())
        print(f"\t6. {len(res)}")

    if filters.country_of_origin and filters.country_of_origin != "all":
        res = tuple(
            s for s in res if s.country.lower() == filters.country_of_origin.lower()
        )
        print(f"\t7. {len(res)}")

    if filters.adjusted_age and filters.adjusted_age != "all":
        try:
            age_value = int(filters.adjusted_age)
            res = tuple(
                s for s in res if s.adjusted_age and s.adjusted_age >= age_value
            )
        except ValueError:
            pass  # Ignore invalid age filter
        print(f"\t8. {len(res)}")

    if filters.single_placement is not None and filters.single_placement != "all":
        if filters.single_placement.lower() == "yes":
            res = tuple(s for s in res if s.single_placement is True)
        elif filters.single_placement.lower() == "no":
            res = tuple(s for s in res if s.single_placement is True)
        print(f"\t9. {len(res)}")

    if filters.double_placement is not None and filters.double_placement != "all":
        if filters.double_placement.lower() == "yes":
            res = tuple(s for s in res if s.double_placement is True)
        elif filters.double_placement.lower() == "no":
            res = tuple(s for s in res if s.double_placement is False)
        print(f"\t10. {len(res)}")

    if filters.program_types is not None and isinstance(filters.program_types, tuple):
        if len(filters.program_types) == 0:
            pass
        else:
            mapping = {
                "10-month-aug": "August 10",
                "5-month-aug": "August 5",
                "10-month-jan": "January 10",
                "5-month-jan": "January 5",
            }
            p_types = [mapping.get(x) for x in filters.program_types]
            res = tuple(s for s in res if any([x in s.program_type for x in p_types]))
            print(f"\t11. {len(res)}")

    if filters.early_placement is not None and filters.early_placement != "all":
        if filters.early_placement.lower() == "yes":
            res = tuple(s for s in res if "EP" in s.usahsid.upper())
        else:
            res = tuple(s for s in res if "EP" not in s.usahsid.upper())
        print(f"\t12. {len(res)}")

    # TODO: Confirm if this worked
    if filters.hasVideo is not None and filters.hasVideo is True:
        res = tuple(s for s in res if s.media_link != "")
        print(f"\t13. {len(res)}")

    if filters.religiousPractice is not None and filters.religiousPractice != "all":
        mapping = {
            "none": 0,
            "some": 1,
            "often": 2,
        }
        res = tuple(
            s
            for s in res
            if s.religious_frequency == mapping[filters.religiousPractice]
        )
        print(f"\t14. {len(res)}")

    if filters.grants_options is not None and len(filters.grants_options) != 0:
        if "grant" in filters.grants_options:
            res = tuple(
                x
                for x in res
                if x.usahsid.upper()[0:3] in ["CBE", "CBX", "FAO", "FLX", "YES", "CBG"]
            )
        else:
            res = tuple(
                student
                for student in res
                if student.usahsid.lower()[0:3] in filters.grants_options
            )
        print(f"\t15. {len(res)}")

    # TODO: Switch to embeddings
    if filters.photo_search is not None and filters.photo_search != "":
        res = tuple(
            s
            for s in res
            if fuzz.partial_ratio(
                filters.photo_search, s.photo_comments, processor=utils.default_process
            )
            >= 86
        )
        print(f"\t16. {len(res)}")

    if filters.free_text is not None and filters.free_text != "":
        x: list[FullStudent] = []

        for student in res:
            if (
                fuzz.ratio(
                    filters.free_text,
                    student.first_name,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.photo_comments,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.ratio(
                    filters.free_text, student.religion, processor=utils.default_process
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.allergy_comments,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.dietary_restrictions,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    " ".join(w for w in student.health_comments),
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    " ".join(w for w in student.favorite_subjects),
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    " ".join(w for w in student.selected_interests),
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    " ".join(w for w in student.free_text_interests),
                    processor=utils.default_process,
                )
            ) >= 80:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.intro_message,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.message_to_host_family,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue
            if (
                fuzz.partial_ratio(
                    filters.free_text,
                    student.message_from_natural_family,
                    processor=utils.default_process,
                )
            ) >= 86:
                x.append(student)
                continue

        res = tuple(w for w in x)
        print(f"\t17. {len(res)}")
        # TODO: Stop after 21 results, then continue to do the analysis in the background
        # TODO: Preprocess everything beforehand so that any string is ever processed once.
    return res
