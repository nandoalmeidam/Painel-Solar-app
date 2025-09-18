from typing import Any, Dict
import re
from aiohttp import ClientSession

from sems_portal_api.sems_plant_details import (
    get_powerflow,
    get_plant_details,
    get_inverter_details,
)


def get_value_by_key(array_of_dicts, key_to_find):
    return next(
        (dct["value"] for dct in array_of_dicts if dct["key"] == key_to_find), None
    )


def get_value_by_target_key(array_of_dicts, key_to_find):
    return next(
        (dct["value"] for dct in array_of_dicts if dct["target_key"] == key_to_find),
        None,
    )


def extract_number(s):
    """Remove units from string and turn to number."""

    # Match one or more digits at the beginning of the string
    match = re.match(r"(\d+(\.\d+)?)", s)
    if match:
        return float(match.group(1))

    return None


async def get_collated_plant_details(
    session: ClientSession, power_station_id: str, token: str
) -> Any:
    """Get powerplant details."""

    plant_information = await get_powerflow(
        session=session,
        power_station_id=power_station_id,
        token=token,
    )
    if isinstance(plant_information, dict):
        # usa "powerflow" se existir; caso contrário, usa o próprio dict
        powerflow_information = plant_information.get("powerflow", plant_information)
    else:
        powerflow_information = None

    plantDetails = await get_plant_details(
        session=session,
        power_station_id=power_station_id,
        token=token,
    ) or {}

    inverterDetails = await get_inverter_details(
        session=session,
        power_station_id=power_station_id,
        token=token,
    ) or []

    info = plantDetails.get("info", {}) if isinstance(plantDetails, dict) else {}
    kpi  = plantDetails.get("kpi", {}) if isinstance(plantDetails, dict) else {}

    data: Dict[str, Any] = {
        "powerPlant": {
            "info": {
                "name": info.get("stationname"),
                "model": "GoodWe",
                "powerstation_id": info.get("powerstation_id"),
                "stationname": info.get("stationname"),
                "battery_capacity": info.get("battery_capacity"),
                "capacity": info.get("capacity"),
                "monthGeneration": kpi.get("month_generation"),
                "generationToday": kpi.get("power"),
                "allTimeGeneration": kpi.get("total_power"),
                "todayIncome": kpi.get("day_income"),
                "totalIncome": kpi.get("total_income"),
            },
            "inverters": [
                {
                    "name": inverter.get("sn"),
                    "model": get_value_by_key(inverter.get("dict", {}).get("left", []), "dmDeviceType"),
                    "innerTemp": extract_number(
                        get_value_by_key(inverter.get("dict", {}).get("left", []), "innerTemp")
                    ),
                }
                for inverter in inverterDetails
                if isinstance(inverter, dict)
            ],
        }
    }

    if powerflow_information:
        data["powerPlant"]["info"].update(
            {
                "generationLive": extract_number(powerflow_information.get("pv")),
                "pvStatus": powerflow_information.get("pvStatus"),
                "battery": extract_number(powerflow_information.get("bettery")),
                "batteryStatus": powerflow_information.get("betteryStatus"),
                "batteryStatusStr": powerflow_information.get("betteryStatusStr"),
                "houseLoad": extract_number(powerflow_information.get("load")),
                "houseLoadStatus": powerflow_information.get("loadStatus"),
                "gridLoad": extract_number(powerflow_information.get("grid")),
                "gridLoadStatus": powerflow_information.get("gridStatus"),
                "soc": powerflow_information.get("soc"),
                "socText": extract_number(powerflow_information.get("socText")),
            }
        )

    return data