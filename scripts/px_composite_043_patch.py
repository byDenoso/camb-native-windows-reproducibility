from __future__ import annotations

import sys
from pathlib import Path


TYPE_BLOCK = r'''

    ! T-043 frozen effective closure: deformed PEER early pNGB plus a
    ! separately conserved low-sound-speed late fluid representing the
    ! condensate-reflection-protected P(X) endpoint. The microscopic
    ! composite DM trigger is NOT implemented in this class.
    type, extends(TEarlyQuintessence) :: TPeerPXFluid
        real(dl) :: eta = 0.1_dl
        real(dl) :: late_w = -0.9927201860086855_dl
        real(dl) :: late_cs2 = 0.0009124677221481836_dl
        real(dl) :: late_frac0 = 1._dl
        real(dl) :: late_grhov0 = 0._dl
    contains
        procedure :: Vofphi => TPeerPXFluid_EarlyVofPhi
        procedure :: Init => TPeerPXFluid_Init
        procedure :: BackgroundDensityAndPressure => TPeerPXFluid_BackgroundDensityAndPressure
        procedure :: PerturbedStressEnergy => TPeerPXFluid_PerturbedStressEnergy
        procedure :: PerturbationEvolve => TPeerPXFluid_PerturbationEvolve
        procedure, nopass :: PythonClass => TPeerPXFluid_PythonClass
        procedure, nopass :: SelfPointer => TPeerPXFluid_SelfPointer
    end type TPeerPXFluid
'''

METHOD_BLOCK = r'''

    function TPeerPXFluid_EarlyVofPhi(this, phi, deriv) result(V)
    class(TPeerPXFluid) :: this
    real(dl) :: phi, V, theta, u, sintheta, costheta, fp, fpp
    integer :: deriv
    real(dl), parameter :: units = MPC_in_sec**2 /Tpl**2

    theta = phi/this%f
    costheta = cos(theta)
    sintheta = sin(theta)
    u = 1._dl - costheta
    fp = 3._dl*u**2 + 4._dl*this%eta*u**3
    fpp = (6._dl*u + 12._dl*this%eta*u**2)*sintheta**2 + fp*costheta
    if (deriv == 0) then
        V = units*this%m**2*this%f**2*u**3*(1._dl + this%eta*u)
    else if (deriv == 1) then
        V = units*this%m**2*this%f*fp*sintheta
    else if (deriv == 2) then
        V = units*this%m**2*fpp
    else
        V = 0._dl
    end if
    end function TPeerPXFluid_EarlyVofPhi

    subroutine TPeerPXFluid_Init(this, State)
    class(TPeerPXFluid), intent(inout) :: this
    class(TCAMBdata), intent(in), target :: State
    real(dl) :: phi, phidot, early_today

    this%frac_lambda0 = 0._dl
    call this%TEarlyQuintessence%Init(State)
    if (global_error_flag /= 0) return
    this%is_cosmological_constant = .false.
    this%num_perturb_equations = 4

    call this%ValsAta(1._dl, phi, phidot)
    early_today = 0.5_dl*phidot**2 + TPeerPXFluid_EarlyVofPhi(this, phi, 0)
    if (State%grhov <= 0._dl) then
        error stop 'TPeerPXFluid requires positive present dark-energy density'
    end if
    if (early_today >= State%grhov) then
        error stop 'TPeerPXFluid early component exceeds present dark-energy closure'
    end if
    this%late_grhov0 = State%grhov - early_today
    this%late_frac0 = this%late_grhov0 / State%grhov
    end subroutine TPeerPXFluid_Init

    subroutine TPeerPXFluid_BackgroundDensityAndPressure(this, grhov, a, grhov_t, w)
    class(TPeerPXFluid), intent(inout) :: this
    real(dl), intent(in) :: grhov, a
    real(dl), intent(out) :: grhov_t
    real(dl), optional, intent(out) :: w
    real(dl) :: phi, phidot, Ve, early_rho, early_p, late_rho, total_p, a2

    if (a <= 0._dl) then
        grhov_t = 0._dl
        if (present(w)) w = -1._dl
        return
    end if

    late_rho = this%late_grhov0 * a**(-1._dl - 3._dl*this%late_w)
    early_rho = 0._dl
    early_p = 0._dl
    if (a >= this%astart) then
        a2 = a**2
        call this%ValsAta(a, phi, phidot)
        Ve = TPeerPXFluid_EarlyVofPhi(this, phi, 0)
        early_rho = 0.5_dl*phidot**2 + a2*Ve
        early_p = 0.5_dl*phidot**2 - a2*Ve
    end if
    grhov_t = early_rho + late_rho
    if (present(w)) then
        total_p = early_p + this%late_w*late_rho
        if (grhov_t > 0._dl) then
            w = total_p/grhov_t
        else
            w = -1._dl
        end if
    end if
    end subroutine TPeerPXFluid_BackgroundDensityAndPressure

    subroutine TPeerPXFluid_PerturbedStressEnergy(this, dgrhoe, dgqe, &
        a, dgq, dgrho, grho, grhov_t, w, gpres_noDE, etak, adotoa, k, kf1, &
        ay, ayprime, w_ix)
    class(TPeerPXFluid), intent(inout) :: this
    real(dl), intent(out) :: dgrhoe, dgqe
    real(dl), intent(in) :: a, dgq, dgrho, grho, grhov_t, w, gpres_noDE
    real(dl), intent(in) :: etak, adotoa, k, kf1
    real(dl), intent(in) :: ay(*)
    real(dl), intent(inout) :: ayprime(*)
    integer, intent(in) :: w_ix
    real(dl) :: phi, phidot, early_dgrho, early_dgq, late_rho

    early_dgrho = 0._dl
    early_dgq = 0._dl
    if (a >= this%astart) then
        call this%ValsAta(a, phi, phidot)
        early_dgrho = phidot*ay(w_ix+1) + ay(w_ix)*a**2*TPeerPXFluid_EarlyVofPhi(this, phi, 1)
        early_dgq = k*phidot*ay(w_ix)
    end if
    late_rho = this%late_grhov0 * a**(-1._dl - 3._dl*this%late_w)
    dgrhoe = early_dgrho + ay(w_ix+2)*late_rho
    dgqe = early_dgq + ay(w_ix+3)*late_rho*(1._dl + this%late_w)
    end subroutine TPeerPXFluid_PerturbedStressEnergy

    subroutine TPeerPXFluid_PerturbationEvolve(this, ayprime, w, w_ix, &
        a, adotoa, k, z, y)
    class(TPeerPXFluid), intent(in) :: this
    real(dl), intent(inout) :: ayprime(:)
    real(dl), intent(in) :: a, adotoa, w, k, z, y(:)
    integer, intent(in) :: w_ix
    real(dl) :: phi, phidot, de, ve, dl, vl, Hv3_over_k, one_plus_w

    de = y(w_ix)
    ve = y(w_ix+1)
    dl = y(w_ix+2)
    vl = y(w_ix+3)

    if (a >= this%astart) then
        call this%ValsAta(a, phi, phidot)
        ayprime(w_ix) = ve
        ayprime(w_ix+1) = -2._dl*adotoa*ve - k*z*phidot - k**2*de &
            - a**2*de*TPeerPXFluid_EarlyVofPhi(this, phi, 2)
    else
        ayprime(w_ix) = 0._dl
        ayprime(w_ix+1) = 0._dl
    end if

    one_plus_w = 1._dl + this%late_w
    if (abs(one_plus_w) > 1.e-12_dl .and. k /= 0._dl) then
        Hv3_over_k = 3._dl*adotoa*vl/k
        ayprime(w_ix+2) = -3._dl*adotoa*(this%late_cs2-this%late_w) &
            *(dl + one_plus_w*Hv3_over_k) - one_plus_w*k*vl - one_plus_w*k*z
        ayprime(w_ix+3) = -adotoa*(1._dl-3._dl*this%late_cs2)*vl &
            + k*this%late_cs2*dl/one_plus_w
    else
        ayprime(w_ix+2) = 0._dl
        ayprime(w_ix+3) = 0._dl
    end if
    end subroutine TPeerPXFluid_PerturbationEvolve

    function TPeerPXFluid_PythonClass()
    character(LEN=:), allocatable :: TPeerPXFluid_PythonClass
    TPeerPXFluid_PythonClass = 'PeerPXFluid'
    end function TPeerPXFluid_PythonClass

    subroutine TPeerPXFluid_SelfPointer(cptr, P)
    use iso_c_binding
    Type(c_ptr) :: cptr
    Type(TPeerPXFluid), pointer :: PType
    class(TPythonInterfacedClass), pointer :: P
    call c_f_pointer(cptr, PType)
    P => PType
    end subroutine TPeerPXFluid_SelfPointer
'''

PY_BLOCK = r'''

@fortran_class
class PeerPXFluid(EarlyQuintessence):
    """T-043 effective PEER-early + low-c_s protected-P(X) late fluid.

    This is the frozen linear effective closure used for the observational
    holdout. It does not implement the microscopic composite DM trigger.
    """

    _fields_ = (
        ("eta", c_double),
        ("late_w", c_double),
        ("late_cs2", c_double),
        ("late_frac0", c_double),
        ("late_grhov0", c_double),
    )
    _fortran_class_name_ = "TPeerPXFluid"

    def set_params(
        self,
        eta=0.1,
        f=0.05,
        m=5e-54,
        theta_i=2.89155,
        use_zc=True,
        zc=10**3.81,
        fde_zc=0.088,
        late_w=-0.9927201860086855,
        late_cs2=0.0009124677221481836,
    ):
        super().set_params(n=3.0, f=f, m=m, theta_i=theta_i, use_zc=use_zc, zc=zc, fde_zc=fde_zc)
        self.frac_lambda0 = 0.0
        self.eta = eta
        self.late_w = late_w
        self.late_cs2 = late_cs2
        return self
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_texts(f90: str, py: str, camb: str) -> tuple[str, str, str]:
    f90 = replace_once(
        f90,
        "    end type TPeerAxionTwoField\n",
        "    end type TPeerAxionTwoField\n" + TYPE_BLOCK,
        "Fortran TPeerPXFluid type insertion",
    )
    f90 = replace_once(
        f90,
        "    public TQuintessence, TEarlyQuintessence, TDeformedEarlyQuintessence, TPeerAxionTwoField",
        "    public TQuintessence, TEarlyQuintessence, TDeformedEarlyQuintessence, TPeerAxionTwoField, TPeerPXFluid",
        "Fortran public list",
    )
    f90 = replace_once(
        f90,
        "    function TDeformedEarlyQuintessence_PythonClass()",
        METHOD_BLOCK + "\n    function TDeformedEarlyQuintessence_PythonClass()",
        "Fortran method insertion",
    )
    py = replace_once(
        py,
        "\n\n# short names for models that support w/wa",
        PY_BLOCK + "\n\n# short names for models that support w/wa",
        "Python class insertion",
    )
    old = (
        "    else if (DarkEneryModel == 'PEERAXIONTWOFIELD') then\n"
        "        allocate(TPeerAxionTwoField :: P%DarkEnergy)"
    )
    new = old + (
        "\n    else if (DarkEneryModel == 'PEERPXFLUID') then\n"
        "        allocate(TPeerPXFluid :: P%DarkEnergy)"
    )
    camb = replace_once(camb, old, new, "CAMB allocation insertion")
    return f90, py, camb


def patch(root: Path) -> None:
    f90_path = root / "fortran" / "DarkEnergyQuintessence.f90"
    py_path = root / "camb" / "dark_energy.py"
    camb_path = root / "fortran" / "camb.f90"
    f90, py, camb = patch_texts(f90_path.read_text(), py_path.read_text(), camb_path.read_text())
    f90_path.write_text(f90)
    py_path.write_text(py)
    camb_path.write_text(camb)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: px_composite_043_patch.py /path/to/CAMB")
    patch(Path(sys.argv[1]).resolve())
