from __future__ import annotations

import sys
from pathlib import Path


TYPE_BLOCK = r'''
    ! Deformed early pNGB comparator with the standard Lambda closure.
    type, extends(TEarlyQuintessence) :: TDeformedEarlyQuintessence
        real(dl) :: eta = 0.1_dl
    contains
        procedure :: Vofphi => TDeformedEarlyQuintessence_VofPhi
        procedure, nopass :: PythonClass => TDeformedEarlyQuintessence_PythonClass
        procedure, nopass :: SelfPointer => TDeformedEarlyQuintessence_SelfPointer
    end type TDeformedEarlyQuintessence

    ! Lambda-free dual-scale model: early deformed pNGB + late standard cosine axion.
    type, extends(TEarlyQuintessence) :: TPeerAxionTwoField
        real(dl) :: eta = 0.1_dl
        real(dl) :: late_f = 1._dl
        real(dl) :: late_theta_i = 2.34159265358979323846_dl
        real(dl) :: late_amp = 0.62_dl
        real(dl), dimension(:), allocatable :: late_phi_a, late_phidot_a
        real(dl), private, dimension(:), allocatable :: late_ddphi_a, late_ddphidot_a
        real(dl) :: late_w0 = -1._dl
        real(dl) :: late_rho_ratio0 = 0._dl
    contains
        procedure :: Vofphi => TPeerAxionTwoField_EarlyVofPhi
        procedure :: Init => TPeerAxionTwoField_Init
        procedure :: BackgroundDensityAndPressure => TPeerAxionTwoField_BackgroundDensityAndPressure
        procedure :: PerturbedStressEnergy => TPeerAxionTwoField_PerturbedStressEnergy
        procedure :: PerturbationEvolve => TPeerAxionTwoField_PerturbationEvolve
        procedure, private :: LateVofPhi => TPeerAxionTwoField_LateVofPhi
        procedure, private :: LateValsAta => TPeerAxionTwoField_LateValsAta
        procedure, nopass :: PythonClass => TPeerAxionTwoField_PythonClass
        procedure, nopass :: SelfPointer => TPeerAxionTwoField_SelfPointer
    end type TPeerAxionTwoField
'''

METHOD_BLOCK = r'''

    function TDeformedEarlyQuintessence_VofPhi(this, phi, deriv) result(V)
    class(TDeformedEarlyQuintessence) :: this
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
        V = units*this%m**2*this%f**2*u**3*(1._dl + this%eta*u) &
            + this%frac_lambda0*this%State%grhov
    else if (deriv == 1) then
        V = units*this%m**2*this%f*fp*sintheta
    else if (deriv == 2) then
        V = units*this%m**2*fpp
    else
        V = 0._dl
    end if
    end function TDeformedEarlyQuintessence_VofPhi

    function TPeerAxionTwoField_EarlyVofPhi(this, phi, deriv) result(V)
    class(TPeerAxionTwoField) :: this
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
    end function TPeerAxionTwoField_EarlyVofPhi

    function TPeerAxionTwoField_LateVofPhi(this, phi, deriv) result(V)
    class(TPeerAxionTwoField) :: this
    real(dl) :: phi, V, theta
    integer :: deriv

    theta = phi/this%late_f
    if (deriv == 0) then
        V = this%late_amp*this%State%grhov*(1._dl - cos(theta))
    else if (deriv == 1) then
        V = this%late_amp*this%State%grhov*sin(theta)/this%late_f
    else if (deriv == 2) then
        V = this%late_amp*this%State%grhov*cos(theta)/this%late_f**2
    else
        V = 0._dl
    end if
    end function TPeerAxionTwoField_LateVofPhi

    subroutine TPeerAxionTwoField_EvolveBackground(this, num, a, y, yprime)
    class(TPeerAxionTwoField) :: this
    integer :: num
    real(dl) :: y(num), yprime(num), a
    real(dl) :: a2, phie, phile, pdote, pdotl, grhode, adot

    a2 = a**2
    phie = y(1)
    pdote = y(2)/a2
    phile = y(3)
    pdotl = y(4)/a2
    grhode = a2*(0.5_dl*(pdote**2 + pdotl**2) + a2*( &
        TPeerAxionTwoField_EarlyVofPhi(this, phie, 0) + &
        TPeerAxionTwoField_LateVofPhi(this, phile, 0)))
    adot = sqrt((this%State%grho_no_de(a) + grhode)/3._dl)
    yprime(1) = pdote/adot
    yprime(2) = -a2**2*TPeerAxionTwoField_EarlyVofPhi(this, phie, 1)/adot
    yprime(3) = pdotl/adot
    yprime(4) = -a2**2*TPeerAxionTwoField_LateVofPhi(this, phile, 1)/adot
    end subroutine TPeerAxionTwoField_EvolveBackground

    subroutine TPeerAxionTwoField_Init(this, State)
    class(TPeerAxionTwoField), intent(inout) :: this
    class(TCAMBdata), intent(in), target :: State
    integer, parameter :: NumEqs = 4
    integer :: ind, i, ix, tot_points, max_ix
    real(dl) :: c(24), work(NumEqs,9), y(NumEqs), afrom, aend, a, a2
    real(dl) :: early_term, late_term, Ve, Vl, kine, kinl
    real(dl), parameter :: splZero = 0._dl

    this%frac_lambda0 = 0._dl
    call this%TEarlyQuintessence%Init(State)
    if (global_error_flag /= 0) return
    this%is_cosmological_constant = .false.
    this%num_perturb_equations = 4

    tot_points = size(this%sampled_a)
    if (allocated(this%late_phi_a)) deallocate(this%late_phi_a)
    if (allocated(this%late_phidot_a)) deallocate(this%late_phidot_a)
    if (allocated(this%late_ddphi_a)) deallocate(this%late_ddphi_a)
    if (allocated(this%late_ddphidot_a)) deallocate(this%late_ddphidot_a)
    allocate(this%late_phi_a(tot_points), this%late_phidot_a(tot_points))
    allocate(this%late_ddphi_a(tot_points), this%late_ddphidot_a(tot_points))

    y(1) = this%theta_i*this%f
    y(2) = 0._dl
    y(3) = this%late_theta_i*this%late_f
    y(4) = 0._dl
    this%phi_a(1) = y(1)
    this%phidot_a(1) = 0._dl
    this%late_phi_a(1) = y(3)
    this%late_phidot_a(1) = 0._dl

    ind = 1
    afrom = this%sampled_a(1)
    do i = 1, tot_points-1
        aend = this%sampled_a(i+1)
        call dverk(this, NumEqs, TPeerAxionTwoField_EvolveBackground, afrom, y, &
            aend, this%integrate_tol, ind, c, NumEqs, work)
        if (global_error_flag /= 0) return
        a2 = aend**2
        this%phi_a(i+1) = y(1)
        this%phidot_a(i+1) = y(2)/a2
        this%late_phi_a(i+1) = y(3)
        this%late_phidot_a(i+1) = y(4)/a2
    end do

    call spline(this%sampled_a, this%phi_a, tot_points, splZero, splZero, this%ddphi_a)
    call spline(this%sampled_a, this%phidot_a, tot_points, splZero, splZero, this%ddphidot_a)
    call spline(this%sampled_a, this%late_phi_a, tot_points, splZero, splZero, this%late_ddphi_a)
    call spline(this%sampled_a, this%late_phidot_a, tot_points, splZero, splZero, this%late_ddphidot_a)

    do i = 1, tot_points
        a = this%sampled_a(i)
        a2 = a**2
        Ve = TPeerAxionTwoField_EarlyVofPhi(this, this%phi_a(i), 0)
        Vl = TPeerAxionTwoField_LateVofPhi(this, this%late_phi_a(i), 0)
        kine = 0.5_dl*this%phidot_a(i)**2
        kinl = 0.5_dl*this%late_phidot_a(i)**2
        early_term = a2*(kine + a2*Ve)
        late_term = a2*(kinl + a2*Vl)
        this%fde(i) = early_term/(this%State%grho_no_de(a) + early_term + late_term)
    end do
    call spline(this%sampled_a, this%fde, tot_points, splZero, splZero, this%ddfde)
    max_ix = maxloc(this%fde, dim=1)
    this%fde_zc = this%fde(max_ix)
    this%zc = 1._dl/this%sampled_a(max_ix) - 1._dl

    ix = tot_points
    Vl = TPeerAxionTwoField_LateVofPhi(this, this%late_phi_a(ix), 0)
    kinl = 0.5_dl*this%late_phidot_a(ix)**2
    this%late_w0 = (kinl - Vl)/(kinl + Vl)
    this%late_rho_ratio0 = (kinl + Vl)/this%State%grhov
    end subroutine TPeerAxionTwoField_Init

    subroutine TPeerAxionTwoField_LateValsAta(this, a, aphi, aphidot)
    class(TPeerAxionTwoField) :: this
    real(dl), intent(in) :: a
    real(dl), intent(out) :: aphi, aphidot
    real(dl) :: a0, b0, ho2o6, delta, da
    integer :: ix, nall

    nall = size(this%sampled_a)
    if (a >= 0.9999999_dl) then
        aphi = this%late_phi_a(nall)
        aphidot = this%late_phidot_a(nall)
        return
    else if (a < this%astart) then
        aphi = this%late_phi_a(1)
        aphidot = 0._dl
        return
    else if (a > this%max_a_log) then
        delta = a - this%max_a_log
        ix = this%npoints_log + int(delta/this%da)
    else
        delta = log(a) - this%log_astart
        ix = int(delta/this%dloga) + 1
    end if
    ix = max(1, min(ix, nall-1))
    da = this%sampled_a(ix+1) - this%sampled_a(ix)
    a0 = (this%sampled_a(ix+1) - a)/da
    b0 = 1._dl - a0
    ho2o6 = da**2/6._dl
    aphi = b0*this%late_phi_a(ix+1) + a0*(this%late_phi_a(ix) - b0*( &
        (a0+1._dl)*this%late_ddphi_a(ix) + (2._dl-a0)*this%late_ddphi_a(ix+1))*ho2o6)
    aphidot = b0*this%late_phidot_a(ix+1) + a0*(this%late_phidot_a(ix) - b0*( &
        (a0+1._dl)*this%late_ddphidot_a(ix) + (2._dl-a0)*this%late_ddphidot_a(ix+1))*ho2o6)
    end subroutine TPeerAxionTwoField_LateValsAta

    subroutine TPeerAxionTwoField_BackgroundDensityAndPressure(this, grhov, a, grhov_t, w)
    class(TPeerAxionTwoField), intent(inout) :: this
    real(dl), intent(in) :: grhov, a
    real(dl), intent(out) :: grhov_t
    real(dl), optional, intent(out) :: w
    real(dl) :: phie, pdote, phile, pdotl, Ve, Vl, kinetic, potential, a2

    if (a >= this%astart) then
        a2 = a**2
        call this%ValsAta(a, phie, pdote)
        call this%LateValsAta(a, phile, pdotl)
        Ve = TPeerAxionTwoField_EarlyVofPhi(this, phie, 0)
        Vl = TPeerAxionTwoField_LateVofPhi(this, phile, 0)
        kinetic = 0.5_dl*(pdote**2 + pdotl**2)
        potential = a2*(Ve + Vl)
        grhov_t = kinetic + potential
        if (present(w)) w = (kinetic - potential)/grhov_t
    else
        grhov_t = 0._dl
        if (present(w)) w = -1._dl
    end if
    end subroutine TPeerAxionTwoField_BackgroundDensityAndPressure

    subroutine TPeerAxionTwoField_PerturbedStressEnergy(this, dgrhoe, dgqe, &
        a, dgq, dgrho, grho, grhov_t, w, gpres_noDE, etak, adotoa, k, kf1, &
        ay, ayprime, w_ix)
    class(TPeerAxionTwoField), intent(inout) :: this
    real(dl), intent(out) :: dgrhoe, dgqe
    real(dl), intent(in) :: a, dgq, dgrho, grho, grhov_t, w, gpres_noDE
    real(dl), intent(in) :: etak, adotoa, k, kf1
    real(dl), intent(in) :: ay(*)
    real(dl), intent(inout) :: ayprime(*)
    integer, intent(in) :: w_ix
    real(dl) :: phie, pdote, phile, pdotl, de, ve, dlfield, vlfield

    call this%ValsAta(a, phie, pdote)
    call this%LateValsAta(a, phile, pdotl)
    de = ay(w_ix)
    ve = ay(w_ix+1)
    dlfield = ay(w_ix+2)
    vlfield = ay(w_ix+3)
    dgrhoe = pdote*ve + de*a**2*TPeerAxionTwoField_EarlyVofPhi(this, phie, 1) &
        + pdotl*vlfield + dlfield*a**2*TPeerAxionTwoField_LateVofPhi(this, phile, 1)
    dgqe = k*(pdote*de + pdotl*dlfield)
    end subroutine TPeerAxionTwoField_PerturbedStressEnergy

    subroutine TPeerAxionTwoField_PerturbationEvolve(this, ayprime, w, w_ix, &
        a, adotoa, k, z, y)
    class(TPeerAxionTwoField), intent(in) :: this
    real(dl), intent(inout) :: ayprime(:)
    real(dl), intent(in) :: a, adotoa, w, k, z, y(:)
    integer, intent(in) :: w_ix
    real(dl) :: phie, pdote, phile, pdotl, de, ve, dlfield, vlfield

    call this%ValsAta(a, phie, pdote)
    call this%LateValsAta(a, phile, pdotl)
    de = y(w_ix)
    ve = y(w_ix+1)
    dlfield = y(w_ix+2)
    vlfield = y(w_ix+3)
    ayprime(w_ix) = ve
    ayprime(w_ix+1) = -2._dl*adotoa*ve - k*z*pdote - k**2*de &
        - a**2*de*TPeerAxionTwoField_EarlyVofPhi(this, phie, 2)
    ayprime(w_ix+2) = vlfield
    ayprime(w_ix+3) = -2._dl*adotoa*vlfield - k*z*pdotl - k**2*dlfield &
        - a**2*dlfield*TPeerAxionTwoField_LateVofPhi(this, phile, 2)
    end subroutine TPeerAxionTwoField_PerturbationEvolve

    function TDeformedEarlyQuintessence_PythonClass()
    character(LEN=:), allocatable :: TDeformedEarlyQuintessence_PythonClass
    TDeformedEarlyQuintessence_PythonClass = 'DeformedEarlyQuintessence'
    end function TDeformedEarlyQuintessence_PythonClass

    subroutine TDeformedEarlyQuintessence_SelfPointer(cptr, P)
    use iso_c_binding
    Type(c_ptr) :: cptr
    Type(TDeformedEarlyQuintessence), pointer :: PType
    class(TPythonInterfacedClass), pointer :: P
    call c_f_pointer(cptr, PType)
    P => PType
    end subroutine TDeformedEarlyQuintessence_SelfPointer

    function TPeerAxionTwoField_PythonClass()
    character(LEN=:), allocatable :: TPeerAxionTwoField_PythonClass
    TPeerAxionTwoField_PythonClass = 'PeerAxionTwoField'
    end function TPeerAxionTwoField_PythonClass

    subroutine TPeerAxionTwoField_SelfPointer(cptr, P)
    use iso_c_binding
    Type(c_ptr) :: cptr
    Type(TPeerAxionTwoField), pointer :: PType
    class(TPythonInterfacedClass), pointer :: P
    call c_f_pointer(cptr, PType)
    P => PType
    end subroutine TPeerAxionTwoField_SelfPointer
'''

PY_BLOCK = r'''

@fortran_class
class DeformedEarlyQuintessence(EarlyQuintessence):
    """Deformed PEER early pNGB u^3(1+eta*u), with optional Lambda comparator closure."""

    _fields_ = (("eta", c_double),)
    _fortran_class_name_ = "TDeformedEarlyQuintessence"

    def set_params(
        self,
        eta=0.1,
        f=0.05,
        m=5e-54,
        theta_i=2.89155,
        use_zc=True,
        zc=10**3.81,
        fde_zc=0.088,
        frac_lambda0=1.0,
    ):
        super().set_params(n=3.0, f=f, m=m, theta_i=theta_i, use_zc=use_zc, zc=zc, fde_zc=fde_zc)
        self.eta = eta
        self.frac_lambda0 = frac_lambda0
        return self


@fortran_class
class PeerAxionTwoField(EarlyQuintessence):
    """Lambda-free PEER early deformed pNGB plus independent late cosine axion."""

    _fields_ = (
        ("eta", c_double),
        ("late_f", c_double),
        ("late_theta_i", c_double),
        ("late_amp", c_double),
        ("late_phi_a", AllocatableArrayDouble),
        ("late_phidot_a", AllocatableArrayDouble),
        ("__late_ddphi_a", AllocatableArrayDouble),
        ("__late_ddphidot_a", AllocatableArrayDouble),
        ("late_w0", c_double),
        ("late_rho_ratio0", c_double),
    )
    _fortran_class_name_ = "TPeerAxionTwoField"

    def set_params(
        self,
        eta=0.1,
        f=0.05,
        m=5e-54,
        theta_i=2.89155,
        use_zc=True,
        zc=10**3.81,
        fde_zc=0.088,
        late_f=1.0,
        late_theta_i=2.341592653589793,
        late_amp=0.62,
    ):
        super().set_params(n=3.0, f=f, m=m, theta_i=theta_i, use_zc=use_zc, zc=zc, fde_zc=fde_zc)
        self.frac_lambda0 = 0.0
        self.eta = eta
        self.late_f = late_f
        self.late_theta_i = late_theta_i
        self.late_amp = late_amp
        return self
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch(root: Path) -> None:
    f90_path = root / "fortran" / "DarkEnergyQuintessence.f90"
    py_path = root / "camb" / "dark_energy.py"
    camb_path = root / "fortran" / "camb.f90"

    f90 = f90_path.read_text()
    f90 = replace_once(
        f90,
        "    end type TEarlyQuintessence\n\n    procedure(TClassDverk) :: dverk",
        "    end type TEarlyQuintessence\n" + TYPE_BLOCK + "\n    procedure(TClassDverk) :: dverk",
        "Fortran type insertion",
    )
    f90 = replace_once(
        f90,
        "    public TQuintessence, TEarlyQuintessence",
        "    public TQuintessence, TEarlyQuintessence, TDeformedEarlyQuintessence, TPeerAxionTwoField",
        "Fortran public list",
    )
    f90 = replace_once(
        f90,
        "\n\n    !real(dl) function GetOmegaFromInitial",
        METHOD_BLOCK + "\n\n    !real(dl) function GetOmegaFromInitial",
        "Fortran method insertion",
    )
    f90_path.write_text(f90)

    py = py_path.read_text()
    py = replace_once(
        py,
        "\n\n# short names for models that support w/wa",
        PY_BLOCK + "\n\n# short names for models that support w/wa",
        "Python class insertion",
    )
    py_path.write_text(py)

    camb = camb_path.read_text()
    old = "    else if (DarkEneryModel == 'EARLYQUINTESSENCE') then\n        allocate(TEarlyQuintessence :: P%DarkEnergy)"
    new = old + "\n    else if (DarkEneryModel == 'DEFORMEDEARLYQUINTESSENCE') then\n        allocate(TDeformedEarlyQuintessence :: P%DarkEnergy)" + \
        "\n    else if (DarkEneryModel == 'PEERAXIONTWOFIELD') then\n        allocate(TPeerAxionTwoField :: P%DarkEnergy)"
    camb = replace_once(camb, old, new, "CAMB allocation insertion")
    camb_path.write_text(camb)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: peer_axion_twofield_013_patch.py /path/to/CAMB")
    patch(Path(sys.argv[1]).resolve())
