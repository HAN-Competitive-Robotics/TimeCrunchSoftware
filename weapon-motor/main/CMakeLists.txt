idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
)

# WEAPON_MODE is set by flash.py via -DWEAPON_MODE=MODE_CALIBRATE or MODE_TEST.
# For manual idf.py use: idf.py build -DWEAPON_MODE=MODE_CALIBRATE
if(DEFINED WEAPON_MODE)
    target_compile_definitions(${COMPONENT_LIB} PUBLIC ${WEAPON_MODE})
endif()
